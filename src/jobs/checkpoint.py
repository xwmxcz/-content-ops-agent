"""P1-04 pipeline step checkpoints.

A multi-step job that dies partway through has already committed the side effects
of its completed steps. Replaying those steps on retry would repeat them, so each
completed step records a checkpoint and a resumed run starts after the last one.

Checkpoints are a *resume* mechanism, not an idempotency mechanism. They stop the
common case of re-running work whose result is already durable; they do not make
an individual step safe to run twice. Steps that write business data still go
through the P1-02 idempotency ledger, because a crash between a step's own commit
and its checkpoint write leaves the step completed but uncheckpointed, and the
retry will run it again.
"""
from __future__ import annotations

import logging
from typing import Any

from src.storage import ContentStore
from src.utils import metrics
from src.utils.structured_logging import log_event

logger = logging.getLogger(__name__)


def save_step_checkpoint(
    store: ContentStore,
    run_id: str,
    step_index: int,
    step_name: str,
    result_data: dict[str, Any] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    """Record a step's outcome so a retry can skip it."""
    checkpoint = store.save_run_step_checkpoint(
        run_id=run_id,
        step_index=step_index,
        step_name=step_name,
        status=status,
        result_data=result_data,
    )
    if status == "completed":
        metrics.job_checkpoints_saved_total.labels(step_name=step_name).inc()
    log_event(
        logger,
        "run_step_checkpoint_saved",
        run_id=run_id,
        step_index=step_index,
        step_name=step_name,
        status=status,
    )
    return checkpoint


def load_checkpoint(store: ContentStore, run_id: str) -> list[dict[str, Any]]:
    """Every persisted step for a run, ordered by step index."""
    return store.load_run_step_checkpoints(run_id)


def load_completed_steps(store: ContentStore, run_id: str) -> dict[int, dict[str, Any]]:
    """Completed steps keyed by index, for looking up an earlier step's result."""
    return {
        step["step_index"]: step
        for step in store.load_run_step_checkpoints(run_id)
        if step["status"] == "completed"
    }


def get_resume_point(store: ContentStore, run_id: str) -> int:
    """The 1-based index of the first step that still needs to run.

    Returns the lowest index not marked ``completed``, so a hole left by a failed
    step is re-executed instead of skipped.
    """
    return store.get_run_resume_index(run_id)


def is_step_completed(store: ContentStore, run_id: str, step_index: int) -> bool:
    """Whether this step's result is already durable."""
    checkpoint = store.get_run_step_checkpoint(run_id, step_index)
    return bool(checkpoint and checkpoint["status"] == "completed")


def get_step_result(store: ContentStore, run_id: str, step_index: int) -> dict[str, Any] | None:
    """A completed step's stored result, or None if it has not completed."""
    checkpoint = store.get_run_step_checkpoint(run_id, step_index)
    if not checkpoint or checkpoint["status"] != "completed":
        return None
    return checkpoint["result_data"]


def clear_checkpoints(store: ContentStore, run_id: str) -> int:
    """Discard a run's checkpoints once its overall result is durable.

    Called after terminal success. Leaving them behind is harmless for
    correctness but grows the table without bound.
    """
    deleted = store.clear_run_step_checkpoints(run_id)
    if deleted:
        log_event(logger, "run_step_checkpoints_cleared", run_id=run_id, deleted=deleted)
    return deleted


def resume_summary(store: ContentStore, run_id: str) -> dict[str, Any]:
    """Compact view of resume state, for logging and diagnostics."""
    steps = store.load_run_step_checkpoints(run_id)
    completed = [step["step_index"] for step in steps if step["status"] == "completed"]
    return {
        "run_id": run_id,
        "total_checkpoints": len(steps),
        "completed_steps": sorted(completed),
        "resume_from_index": store.get_run_resume_index(run_id),
    }
