"""Account metadata and user-scoped content persistence on PostgreSQL.

TenantSession owns workspace filtering and write validation. Stores returned by
for_user share the engine, not mutable request identity; existing databases are
upgraded only by Alembic.
"""

import logging
import re

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

# Models are re-exported here because callers import them from this module
# (`from src.storage.content_store import Job`). The definition lives in
# .models so the schema can be loaded without the query surface.
from src.storage.models import (  # noqa: F401 -- re-exported public surface
    IDEMPOTENCY_RECORD_STATUSES,
    PROPOSED_ACTION_STATUSES,
    AgentMessage,
    AgentRun,
    AgentRunEvent,
    AgentThread,
    AuthRateLimit,
    AuthSession,
    Base,
    CalendarEvent,
    Content,
    ContentMetrics,
    IdempotencyRecord,
    Job,
    MediaAsset,
    PlatformPublication,
    ProposedAction,
    RunStep,
    User,
)
from src.storage.repositories.action_repository import ActionRepositoryMixin
from src.storage.repositories.calendar_repository import CalendarRepositoryMixin
from src.storage.repositories.content_repository import ContentRepositoryMixin
from src.storage.repositories.idempotency_repository import IdempotencyRepositoryMixin
from src.storage.repositories.job_repository import JobRepositoryMixin
from src.storage.repositories.media_repository import MediaRepositoryMixin
from src.storage.repositories.publication_repository import PublicationRepositoryMixin
from src.storage.repositories.run_repository import RunRepositoryMixin
from src.storage.repositories.thread_repository import ThreadRepositoryMixin
from src.storage.tenancy import TenantSession

logger = logging.getLogger(__name__)


class ContentStore(
    ContentRepositoryMixin,
    CalendarRepositoryMixin,
    MediaRepositoryMixin,
    PublicationRepositoryMixin,
    JobRepositoryMixin,
    ThreadRepositoryMixin,
    RunRepositoryMixin,
    ActionRepositoryMixin,
    IdempotencyRepositoryMixin,
):
    """User-scoped persistence, composed from one mixin per aggregate.

    Every method lives in the repository that owns its aggregate; this class
    holds only the workspace-scoping kernel (engine, session factory, the
    immutable owner) plus the transaction boundary those mixins share.

    They are mixed in rather than injected as separate collaborators on
    purpose: run-event appends, lease reclaims, and idempotency claims each
    need several tables updated in one transaction, so they must share one
    session object.
    """

    # Set to the owning user id by for_user(); None on the unscoped system store
    # used for auth, migrations, and worker discovery. Declared here because
    # __init__ assigns None, which would otherwise pin the inferred type to None
    # and reject the later str assignment in for_user().
    _user_id: str | None

    SessionLocal: sessionmaker

    def __init__(
        self,
        database_url: str | None = None,
        initialize_schema: bool = True,
    ):
        # Only fresh development/test databases may use create_all. Existing
        # databases, API processes, and worker processes use Alembic's schema.
        from src.utils import config

        if database_url is None:
            database_url = config.DATABASE_URL

        url = make_url(database_url)
        if url.get_backend_name() == "sqlite":
            raise ValueError(
                "SQLite is not supported. Set DATABASE_URL to a PostgreSQL DSN, "
                "e.g. postgresql+psycopg://user:password@host:5432/dbname"
            )

        self.database_url = database_url
        self._user_id = None
        self.engine = create_engine(
            database_url,
            echo=False,
            pool_size=config.DB_POOL_SIZE,
            max_overflow=config.DB_MAX_OVERFLOW,
            pool_timeout=config.DB_POOL_TIMEOUT_SECONDS,
            pool_pre_ping=True,
            # Bounds the TCP handshake. Without it an unreachable host hangs the
            # process indefinitely instead of failing fast: pool_timeout applies
            # to pool checkout, not to establishing the socket.
            connect_args={"connect_timeout": config.DB_CONNECT_TIMEOUT_SECONDS},
        )
        if initialize_schema:
            inspector = inspect(self.engine)
            for name in set(inspector.get_table_names()) & set(Base.metadata.tables):
                existing = {column["name"] for column in inspector.get_columns(name)}
                if set(Base.metadata.tables[name].columns.keys()) - existing:
                    self.engine.dispose()
                    raise RuntimeError("Existing database requires `alembic upgrade head`")
            Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, class_=TenantSession)

    @property
    def user_id(self) -> str | None:
        return self._user_id

    def for_user(self, user_id: str) -> "ContentStore":
        if not isinstance(user_id, str) or re.fullmatch(r"[0-9a-f]{32}", user_id) is None:
            raise ValueError("Workspace owner must be a canonical user ID")
        scoped = object.__new__(type(self))
        scoped.database_url = self.database_url
        scoped.engine = self.engine
        scoped.SessionLocal = sessionmaker(
            bind=self.engine,
            class_=TenantSession,
            info={"user_id": user_id},
        )
        scoped._user_id = user_id
        return scoped

    def _get_session(self) -> Session:
        return self.SessionLocal(info={"user_id": self.user_id})
