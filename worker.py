"""RQ worker entry point for production-style background jobs."""
import os

from redis import Redis
from rq import SimpleWorker, Worker

from src.storage import ContentStore
from src.storage.schema import assert_schema_current
from src.utils import config
from src.utils.structured_logging import configure_logging


if __name__ == "__main__":
    configure_logging(config.LOG_LEVEL)
    config.validate_runtime()
    store = ContentStore(
        database_url=config.DATABASE_URL,
        initialize_schema=config.SCHEMA_MANAGEMENT == "create",
    )
    if config.SCHEMA_MANAGEMENT == "validate":
        assert_schema_current(store.engine)
    store.engine.dispose()

    connection = Redis.from_url(config.REDIS_URL)
    worker_cls = SimpleWorker if os.name == "nt" else Worker
    worker = worker_cls([config.JOB_QUEUE_NAME], connection=connection)
    worker.work()
