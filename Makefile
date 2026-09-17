# Developer entrypoints. Every target here is what CI runs, so a green `make check`
# locally means a green pipeline.
PYTHON ?= python
TEST_DATABASE_URL ?= postgresql+psycopg://content_ops:content_ops@127.0.0.1:55432/content_ops_test

.PHONY: install lock lint format typecheck test test-db test-frontend check audit db-up db-down

install:
	$(PYTHON) -m pip install -r requirements-dev.txt
	cd frontend && npm ci

## Re-resolve requirements.lock from requirements.txt (cross-platform, py>=3.11).
lock:
	uv pip compile --universal --python-version 3.11 -o requirements.lock requirements.txt

lint:
	ruff check .
	ruff format --check .

format:
	ruff check . --fix
	ruff format .

typecheck:
	mypy

## Fast unit tests only (database-backed tests are skipped without TEST_DATABASE_URL).
test:
	$(PYTHON) -m pytest -q

## Full suite against a disposable PostgreSQL; refuses to run if the DB is missing.
test-db:
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) REQUIRE_TEST_DATABASE=1 $(PYTHON) -m pytest -q

test-frontend:
	cd frontend && npx vue-tsc --noEmit && npx vitest run

check: lint typecheck test-db test-frontend

audit:
	pip-audit -r requirements.lock
	cd frontend && npm audit --audit-level=high

## Throwaway PostgreSQL for `make test-db`. Never point this at real data.
db-up:
	docker run -d --name content-ops-test-pg \
		-e POSTGRES_USER=content_ops -e POSTGRES_PASSWORD=content_ops -e POSTGRES_DB=content_ops_test \
		-p 55432:5432 postgres:16-alpine

db-down:
	docker rm -f content-ops-test-pg
