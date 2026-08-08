"""RQ worker entry point for production-style background jobs."""
import os

from redis import Redis
from rq import SimpleWorker, Worker

from src.storage import ContentStore
from src.utils import config


if __name__ == "__main__":
    # Ensure the schema exists once in this worker process before jobs start
    # running with initialize_schema=False. Idempotent and safe to race with the
    # API process doing the same against a shared PostgreSQL database.
    ContentStore(database_url=config.DATABASE_URL).engine.dispose()

    connection = Redis.from_url(config.REDIS_URL)
    worker_cls = SimpleWorker if os.name == "nt" else Worker
    worker = worker_cls([config.JOB_QUEUE_NAME], connection=connection)
    worker.work()
