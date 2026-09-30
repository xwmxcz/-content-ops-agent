"""P1-04 lease reaper: recovers jobs whose worker died without releasing the lease.

A worker killed by SIGKILL, OOM, or a node loss cannot run cleanup code, so its
job stays ``running`` forever and never retries. Nothing inside that process can
report the failure — the only observable signal is that the lease stopped being
renewed. This sweep finds those lapsed leases and requeues the jobs.

Reclaiming deliberately does *not* consume a retry attempt: an evicted worker is
not a job error, and charging it against ``max_retries`` would let repeated
infrastructure churn permanently fail a job that never actually ran.

Usage:
    python -m src.jobs.reaper --dry-run
    python -m src.jobs.reaper --execute
    python -m src.jobs.reaper --execute --loop
    python -m src.jobs.reaper --healthcheck

Leases are only recovered while something runs this: deploy ``--execute --loop``
as a long-lived service next to the workers (the Compose stack does).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any

from src.storage import ContentStore
from src.storage.schema import assert_schema_current
from src.utils import config, metrics
from src.utils.structured_logging import configure_logging, log_event

logger = logging.getLogger(__name__)

# The daemon is reported dead after this many sweep intervals without a
# heartbeat: one slow sweep or database blip must not flap the healthcheck.
_HEARTBEAT_STALE_INTERVALS = 3


def find_expired_leases(store: ContentStore, limit: int | None = None) -> list[dict[str, Any]]:
    """Running jobs whose lease has lapsed."""
    return store.find_expired_lease_jobs(limit=limit or config.JOB_REAPER_BATCH_SIZE)


def reclaim_job(store: ContentStore, job: dict[str, Any]) -> bool:
    """Requeue one expired-lease job. False if it was no longer reclaimable.

    The store re-checks expiry inside the UPDATE, so a job whose original worker
    heartbeated between the scan and this call stays with that worker.
    """
    job_id = job["id"]
    worker_id = job.get("worker_id")
    if not worker_id:
        return False

    reclaimed = store.reclaim_job_lease(job_id, worker_id)
    if not reclaimed:
        log_event(
            logger,
            "job_lease_reclaim_skipped",
            job_id=job_id,
            job_type=job.get("job_type"),
            reason="lease_no_longer_expired",
        )
        return False

    metrics.job_lease_reclaimed_total.labels(job_type=job.get("job_type") or "unknown").inc()
    log_event(
        logger,
        "job_lease_reclaimed",
        level=logging.WARNING,
        job_id=job_id,
        job_type=job.get("job_type"),
        previous_worker_id=worker_id,
        attempts=job.get("attempts"),
    )
    return True


def reap_expired_leases(
    store: ContentStore,
    dry_run: bool = True,
    limit: int | None = None,
    requeue: bool = True,
) -> dict[str, Any]:
    """One sweep over expired leases.

    Returns counts so a caller (CLI or scheduled task) can report what happened.
    """
    batch_size = limit or config.JOB_REAPER_BATCH_SIZE
    expired = find_expired_leases(store, limit=batch_size)
    remaining = max(0, batch_size - len(expired))
    pending = store.find_pending_lease_requeues(limit=remaining) if remaining else []
    expired_runs = store.find_expired_run_leases(limit=batch_size)
    log_event(
        logger,
        "job_reaper_scan",
        dry_run=dry_run,
        expired_count=len(expired),
        pending_delivery_count=len(pending),
        expired_pipeline_count=len(expired_runs),
    )

    if dry_run:
        return {
            "found": len(expired) + len(pending),
            "reclaimed": 0,
            "requeued": 0,
            "job_ids": [job["id"] for job in expired + pending],
            "pipeline_found": len(expired_runs),
            "pipeline_failed": 0,
            "run_ids": [run["id"] for run in expired_runs],
        }

    reclaimed_ids: list[str] = []
    for job in expired:
        if reclaim_job(store, job):
            reclaimed_ids.append(job["id"])

    requeued = 0
    delivery_ids = reclaimed_ids + [job["id"] for job in pending]
    if requeue and delivery_ids:
        requeued = _requeue_reclaimed(store, delivery_ids)

    # A pipeline keeps its checkpoints and waits for an explicit user resume.
    # Failing the run and appending its terminal SSE event are one transaction.
    failed_runs = [run["id"] for run in expired_runs if store.fail_expired_run(run["id"]) is not None]

    return {
        "found": len(expired) + len(pending),
        "reclaimed": len(reclaimed_ids),
        "requeued": requeued,
        "job_ids": delivery_ids,
        "pipeline_found": len(expired_runs),
        "pipeline_failed": len(failed_runs),
        "run_ids": failed_runs,
    }


def _requeue_reclaimed(store: ContentStore, job_ids: list[str]) -> int:
    """Put reclaimed jobs back on the queue.

    In ``background`` mode there is no standalone queue to push to; the job row is
    already back at ``queued`` for manual dispatch. Recovery delivery is durable
    in RQ mode: ``next_retry_at`` remains set until enqueue succeeds, so a failed
    delivery is found again by the next sweep even though its lease was cleared.
    """
    if config.JOB_QUEUE_MODE != "rq":
        return 0

    from src.jobs.queue import requeue_job_with_delay

    requeued = 0
    for job_id in job_ids:
        try:
            requeue_job_with_delay(job_id, 0, store.database_url)
            # Starting a delivered job also clears this marker. The predicate
            # keeps this acknowledgement from changing a running/cancelled job.
            store.update_job(job_id, expected_statuses={"queued"}, next_retry_at=None)
            requeued += 1
        except Exception as exc:  # noqa: BLE001 -- per-job isolation: one bad requeue must not stop the sweep
            log_event(
                logger,
                "job_reaper_requeue_failed",
                level=logging.ERROR,
                job_id=job_id,
                error=str(exc),
            )
    return requeued


def heartbeat_is_fresh(heartbeat_path: str | Path, interval_seconds: int, now: float | None = None) -> bool:
    """Whether the reaper daemon completed a sweep iteration recently."""
    try:
        age = (now if now is not None else time.time()) - Path(heartbeat_path).stat().st_mtime
    except OSError:
        return False
    return age < interval_seconds * _HEARTBEAT_STALE_INTERVALS


def _touch_heartbeat(heartbeat_path: str | Path) -> None:
    try:
        path = Path(heartbeat_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError as exc:
        # Recovering jobs matters more than reporting health; an unwritable
        # heartbeat surfaces through the failing healthcheck instead.
        log_event(logger, "job_reaper_heartbeat_failed", level=logging.ERROR, error=str(exc))


async def run_reaper_loop(
    store: ContentStore,
    interval_seconds: int | None = None,
    stop_event: asyncio.Event | None = None,
    heartbeat_path: str | Path | None = None,
) -> None:
    """Sweep expired leases forever, until ``stop_event`` is set.

    Exceptions are swallowed per-iteration: a transient database error must not
    kill the recovery loop, or the very outage that stranded the jobs would also
    disable the mechanism that recovers them. The heartbeat is therefore touched
    after failed sweeps too: it reports that the loop is alive, and restarting
    the reaper would not bring an unreachable database back.
    """
    interval = interval_seconds or config.JOB_REAPER_INTERVAL_SECONDS
    while not (stop_event and stop_event.is_set()):
        try:
            result = reap_expired_leases(store, dry_run=False)
            if result["found"] or result["pipeline_found"]:
                log_event(
                    logger,
                    "job_reaper_sweep_completed",
                    found=result["found"],
                    reclaimed=result["reclaimed"],
                    requeued=result["requeued"],
                    pipeline_failed=result["pipeline_failed"],
                )
        except Exception as exc:  # noqa: BLE001 -- daemon loop must survive any sweep failure
            log_event(
                logger,
                "job_reaper_sweep_failed",
                level=logging.ERROR,
                error=str(exc),
            )

        if heartbeat_path:
            _touch_heartbeat(heartbeat_path)

        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                continue
        await asyncio.sleep(interval)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the lease reaper."""
    parser = argparse.ArgumentParser(description="Recover jobs whose worker lease expired")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report expired leases without reclaiming them (this is the default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually reclaim expired leases (default is dry run)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        default=False,
        help="Run continuously instead of a single sweep",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=None,
        help=f"Sweep interval in loop mode (default: {config.JOB_REAPER_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"Max jobs per sweep (default: {config.JOB_REAPER_BATCH_SIZE})",
    )
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        default=False,
        help="Exit 0 if a --loop daemon sharing this filesystem swept recently, 1 otherwise",
    )

    args = parser.parse_args(argv)
    dry_run = not args.execute

    if args.healthcheck:
        interval = args.interval_seconds or config.JOB_REAPER_INTERVAL_SECONDS
        sys.exit(0 if heartbeat_is_fresh(config.JOB_REAPER_HEARTBEAT_FILE, interval) else 1)

    if args.loop:
        if dry_run:
            parser.error("--loop requires --execute")
        # A long-lived service gets the same startup contract as worker.py:
        # structured logs, fail-closed config, and no sweeping a stale schema.
        configure_logging(config.LOG_LEVEL)
        config.validate_runtime()
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    store = ContentStore(database_url=config.DATABASE_URL, initialize_schema=False)
    try:
        if args.loop:
            if config.SCHEMA_MANAGEMENT == "validate":
                assert_schema_current(store.engine)
            asyncio.run(
                run_reaper_loop(
                    store,
                    interval_seconds=args.interval_seconds,
                    heartbeat_path=config.JOB_REAPER_HEARTBEAT_FILE,
                )
            )
            return

        result = reap_expired_leases(store, dry_run=dry_run, limit=args.limit)
        mode = "DRY RUN" if dry_run else "EXECUTED"
        print(f"\n{mode} - Lease Reaper Results:")
        print(f"  Expired leases found: {result['found']}")
        print(f"  Reclaimed: {result['reclaimed']}")
        print(f"  Requeued: {result['requeued']}")
        print(f"  Expired pipelines: {result['pipeline_found']}")
        print(f"  Pipelines marked failed: {result['pipeline_failed']}")
        if dry_run and result["found"]:
            print("\nNo jobs were reclaimed. Run with --execute to recover them.")
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
