"""Domain-scoped persistence mixins composed into ContentStore.

Each module owns one aggregate: its queries, its invariants, and the models
it touches. They are mixins rather than independent objects because they
share one session and one workspace scope; splitting the session would mean
splitting transactions, which would break the atomicity that run events,
leases, and idempotency claims depend on.
"""

from src.storage.repositories.action_repository import ActionRepositoryMixin
from src.storage.repositories.calendar_repository import CalendarRepositoryMixin
from src.storage.repositories.content_repository import ContentRepositoryMixin
from src.storage.repositories.idempotency_repository import IdempotencyRepositoryMixin
from src.storage.repositories.job_repository import JobRepositoryMixin
from src.storage.repositories.media_repository import MediaRepositoryMixin
from src.storage.repositories.publication_repository import PublicationRepositoryMixin
from src.storage.repositories.run_repository import RunRepositoryMixin
from src.storage.repositories.thread_repository import ThreadRepositoryMixin

__all__ = [
    "ContentRepositoryMixin",
    "CalendarRepositoryMixin",
    "MediaRepositoryMixin",
    "PublicationRepositoryMixin",
    "JobRepositoryMixin",
    "ThreadRepositoryMixin",
    "RunRepositoryMixin",
    "ActionRepositoryMixin",
    "IdempotencyRepositoryMixin",
]
