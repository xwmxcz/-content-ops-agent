FROM python:3.11-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    SCHEMA_MANAGEMENT=validate

WORKDIR /app

# Default to a domestic Debian mirror. Both figures below are from inside the
# build container, which has no proxy: deb.debian.org spent >650s without
# finishing the 9.6MB Packages index and failed the build, while USTC fetched
# every package in ~8s. Override for other regions, e.g.
#   docker compose build --build-arg APT_MIRROR=http://deb.debian.org
# Trixie ships deb822 sources, so the URIs live in debian.sources -- rewriting
# the legacy /etc/apt/sources.list is a no-op on this base image.
ARG APT_MIRROR=http://mirrors.ustc.edu.cn
RUN sed -i "s|http://deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Measured from inside this network with no proxy, which is what the build
# container actually gets (10s sustained read of a botocore wheel):
#   tuna 6880 KB/s, huawei 6512, ustc 6118, tencent 195, aliyun 89,
#   upstream pypi.org 0 KB/s -- 20s without a single byte.
# Do not trust a measurement taken from a shell that exports http(s)_proxy: the
# proxy makes upstream look fast and drags domestic mirrors through an overseas
# exit, which inverts the ranking entirely.
# Override for a network with real upstream reachability, e.g.
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN python -m pip install \
        --index-url "${PIP_INDEX_URL}" --retries 10 --timeout 120 --upgrade pip \
    && python -m pip install \
        --index-url "${PIP_INDEX_URL}" --retries 10 --timeout 120 -r requirements.txt

COPY src ./src
COPY migrations ./migrations
COPY examples ./examples
COPY alembic.ini server.py worker.py gunicorn.conf.py ./

# Run as an unprivileged user. chown the whole /app tree (including the data dir
# below) so the named volume mounted at /app/data inherits app:app ownership on
# first creation and the process can write media/memory files.
RUN mkdir -p /app/data/media /app/data/memory \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["python", "server.py"]


FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
RUN npm run build


FROM nginx:1.27-alpine AS frontend

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
