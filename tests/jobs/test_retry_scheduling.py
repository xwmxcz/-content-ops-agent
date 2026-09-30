"""Retry scheduling without a real queue, provider, timer, or database."""

from __future__ import annotations

import runpy
from pathlib import Path
from unittest.mock import Mock, patch

from src.jobs.queue import requeue_job_with_delay
from src.jobs.runner import run_job
from src.utils import config


def test_background_retry_schedules_dispatch_after_delay(monkeypatch):
    monkeypatch.setattr(config, "JOB_QUEUE_MODE", "background")
    with patch("src.jobs.queue.Timer") as timer:
        requeue_job_with_delay("job_retry", 30, "postgresql+psycopg://test-db")

    timer.assert_called_once_with(30, run_job, args=("job_retry", "postgresql+psycopg://test-db"))
    assert timer.return_value.daemon is True
    timer.return_value.start.assert_called_once_with()


def test_rq_retry_is_scheduled_with_original_database(monkeypatch):
    monkeypatch.setattr(config, "JOB_QUEUE_MODE", "rq")
    with patch("redis.Redis.from_url"), patch("rq.Queue") as queue:
        requeue_job_with_delay("job_retry", 60, "postgresql+psycopg://test-db")

    args = queue.return_value.enqueue_in.call_args.args
    assert args[0].total_seconds() == 60
    assert args[1:] == ("src.jobs.runner.run_job", "job_retry", "postgresql+psycopg://test-db")


def test_worker_enables_the_scheduler_that_delivers_delayed_retries(monkeypatch):
    monkeypatch.setattr(config, "validate_runtime", lambda: None)
    monkeypatch.setattr(config, "SCHEMA_MANAGEMENT", "create")
    worker = Mock()
    with (
        patch("src.storage.ContentStore"),
        patch("src.utils.structured_logging.configure_logging"),
        patch("redis.Redis.from_url"),
        patch("rq.Worker", return_value=worker),
        patch("rq.SimpleWorker", return_value=worker),
    ):
        runpy.run_path(str(Path(__file__).resolve().parents[2] / "worker.py"), run_name="__main__")

    worker.work.assert_called_once_with(with_scheduler=True)
