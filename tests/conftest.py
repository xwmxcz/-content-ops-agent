import os

import pytest

from src.utils import config


# Tests require a PostgreSQL database (SQLite support has been removed).
# Point TEST_DATABASE_URL at a disposable database, e.g.:
#   export TEST_DATABASE_URL=postgresql+psycopg://content_ops:content_ops@localhost:5432/content_ops_test
# The `store` fixture drops and recreates every table around each test, so the
# target database MUST be a throwaway test database, never a real one.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

_requires_pg = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; tests need a disposable PostgreSQL database",
)


@pytest.fixture(autouse=True)
def disable_auth_by_default(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", False)


@pytest.fixture(scope="session")
def pg_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set; tests need a disposable PostgreSQL database")
    from sqlalchemy import create_engine

    engine = create_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def store(pg_engine, monkeypatch):
    """A ContentStore bound to the test PostgreSQL database.

    Every table is dropped and recreated before the test so state never leaks
    between tests (PostgreSQL has no per-file isolation like SQLite did).
    `config.DATABASE_URL` is redirected and the cached singleton cleared so the
    app lifespan and request-time `get_store()` share this same database.
    """
    from src.storage.content_store import Base, ContentStore
    from src.api.dependencies import get_store

    monkeypatch.setattr(config, "DATABASE_URL", TEST_DATABASE_URL)
    Base.metadata.drop_all(pg_engine)
    Base.metadata.create_all(pg_engine)

    get_store.cache_clear()
    s = ContentStore(database_url=TEST_DATABASE_URL, initialize_schema=False)
    try:
        yield s
    finally:
        s.engine.dispose()
        get_store.cache_clear()
