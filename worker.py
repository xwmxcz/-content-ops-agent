"""RQ worker entry point for production-style background jobs."""
import os

from redis import Redis
from rq import SimpleWorker, Worker

from src.utils import config


if __name__ == "__main__":
    connection = Redis.from_url(config.REDIS_URL)
    worker_cls = SimpleWorker if os.name == "nt" else Worker
    worker = worker_cls([config.JOB_QUEUE_NAME], connection=connection)
    worker.work()
