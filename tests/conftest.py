import os

# Tests use disposable PostgreSQL and an explicit development signing key.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SCHEMA_MANAGEMENT", "create")
os.environ.setdefault("AUTH_SECRET_KEY", "test-signing-key-with-at-least-32-characters")

import pytest

from src.utils import config

# Tests require a PostgreSQL database (SQLite support has been removed).
# Point TEST_DATABASE_URL at a disposable database, e.g.:
#   export TEST_DATABASE_URL=postgresql+psycopg://content_ops:content_ops@localhost:5432/content_ops_test
# The `store` fixture drops and recreates every table around each test, so the
# target database MUST be a throwaway test database, never a real one.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

# Locally, missing TEST_DATABASE_URL skips the ~250 database-backed tests so a
# quick `pytest` still works. In CI that would hide half the suite behind a
# green check, so REQUIRE_TEST_DATABASE=1 turns the skip into a hard failure.
_REQUIRE_TEST_DATABASE = os.getenv("REQUIRE_TEST_DATABASE", "").lower() in {"1", "true", "yes"}
_MISSING_DB_REASON = "TEST_DATABASE_URL is not set; tests need a disposable PostgreSQL database"

_requires_pg = pytest.mark.skipif(not TEST_DATABASE_URL, reason=_MISSING_DB_REASON)


def pytest_sessionstart(session):
    if _REQUIRE_TEST_DATABASE and not TEST_DATABASE_URL:
        raise pytest.UsageError(
            "REQUIRE_TEST_DATABASE is set but TEST_DATABASE_URL is empty; "
            "refusing to run a suite that would silently skip every database test."
        )


@pytest.fixture(autouse=True)
def authenticated_fixture_user(monkeypatch, request):
    monkeypatch.setattr(config, "AUTH_SECRET_KEY", "test-signing-key-with-at-least-32-characters")
    if request.node.get_closest_marker("real_auth"):
        return
    # Business tests authenticate one fixture user without exercising login.
    # Account/permission tests opt out and use real database sessions.
    from src.api import security

    monkeypatch.setattr(
        security,
        "authenticate_request",
        lambda request: {
            "id": "11111111111111111111111111111111",
            "username": "fixture_user",
            "session_id": "22222222222222222222222222222222",
        },
    )


_REACHABILITY_CHECKED: set[str] = set()


def _require_reachable_database(database_url: str) -> None:
    """Fail once, with the real reason, if the test database is unreachable.

    Without this, every database-backed test opens its own connection and
    reports a connection error, so a stopped container looks like 250 broken
    tests and takes minutes to say so. Probing the URL once here turns that
    into a single actionable message.
    """
    if database_url in _REACHABILITY_CHECKED:
        return

    from sqlalchemy import create_engine, text

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        # Bounds the TCP handshake: pool_timeout does not cover it, so without
        # this an unreachable host hangs the process instead of reporting the
        # misconfiguration.
        connect_args={"connect_timeout": 10},
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 -- any failure means "not usable"
        # Abort the whole session: an unreachable database is an environment
        # problem, not a test failure, and reporting it once is both faster and
        # more honest than 250 errors that all say the same thing.
        pytest.exit(
            "\nTEST_DATABASE_URL is not reachable "
            f"({type(exc).__name__}: {exc}).\n"
            "Start the disposable test database first, e.g. `make db-up`"
            " (or `mingw32-make db-up` if make is not on PATH).\n",
            returncode=2,
        )
    finally:
        engine.dispose()
    _REACHABILITY_CHECKED.add(database_url)


@pytest.fixture(scope="session")
def pg_engine():
    if not TEST_DATABASE_URL:
        if _REQUIRE_TEST_DATABASE:
            pytest.fail(_MISSING_DB_REASON)
        pytest.skip(_MISSING_DB_REASON)
    from sqlalchemy import create_engine

    _require_reachable_database(TEST_DATABASE_URL)

    engine = create_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
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
    from src.api.dependencies import _file_memory_for, get_system_store
    from src.storage.content_store import Base, ContentStore, User

    monkeypatch.setattr(config, "DATABASE_URL", TEST_DATABASE_URL)
    Base.metadata.drop_all(pg_engine)
    Base.metadata.create_all(pg_engine)

    get_system_store.cache_clear()
    _file_memory_for.cache_clear()
    system = ContentStore(database_url=TEST_DATABASE_URL, initialize_schema=False)
    with system._get_session() as session:
        session.add(
            User(id="11111111111111111111111111111111", username="fixture_user", password_hash="!", is_active=True)
        )
        session.commit()
    s = system.for_user("11111111111111111111111111111111")
    try:
        yield s
    finally:
        s.engine.dispose()
        get_system_store.cache_clear()
        _file_memory_for.cache_clear()
