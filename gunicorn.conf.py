"""Gunicorn configuration for the production-style API container.

docker-compose runs the `api` service with
`gunicorn -c gunicorn.conf.py src.api.main:app`. Local development still uses the
single-process reload server (`python server.py`); this file is only for the
multi-worker path.
"""
import os

# Aliased deliberately. Gunicorn reads every module-level name in this file that
# matches one of its own settings, and it *has* a setting called `config` (the
# -c option) whose value must be a string. Binding the name `config` here made
# gunicorn reject its own config file with "Not a string: <Config object>", so
# the api container crash-looped and never became healthy.
from src.utils import config as app_config

bind = f"{app_config.API_HOST}:{app_config.API_PORT}"

# Disable Gunicorn/Uvicorn's independent X-Forwarded-* preprocessing. The app
# middleware validates the immediate peer against TRUSTED_PROXY_CIDRS before
# accepting X-Forwarded-Proto, avoiding a second, broader trust policy.
forwarded_allow_ips = ""

# Async workers are required: the SSE streaming endpoints hold a long-lived
# connection and poll the event table with `await asyncio.sleep`, so a sync
# worker would block the loop and a single stream would occupy a whole worker.
worker_class = "uvicorn.workers.UvicornWorker"

# Each worker opens its own SQLAlchemy pool, so keep
# workers * (DB_POOL_SIZE + DB_MAX_OVERFLOW) below the database's max_connections.
# The default API load is 3 * (10 + 20) = 90 connections; the separate RQ worker
# process adds up to another (10 + 20) = 30, for 120 worst-case. The compose
# Postgres raises max_connections to 200 (POSTGRES_MAX_CONNECTIONS) to cover that
# with headroom to bump WEB_CONCURRENCY. Postgres' own default is only 100.
workers = int(os.getenv("WEB_CONCURRENCY", "3"))

# SSE handlers are async and keep heartbeating the master, so an open stream does
# not trip this. It only reaps genuinely stuck (event-loop-blocking) workers.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

loglevel = app_config.LOG_LEVEL.lower()
errorlog = "-"
