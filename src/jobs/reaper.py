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
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from src.storage import ContentStore
from src.utils import config, metrics
from src.utils.structured_logging import log_event

logger = logging.getLogger(__name__)


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
    expired = find_expired_leases(store, limit=limit)
    log_event(
        logger,
        "job_reaper_scan",
        dry_run=dry_run,
        expired_count=len(expired),
    )

    if dry_run:
        return {
            "found": len(expired),
            "reclaimed": 0,
            "requeued": 0,
            "job_ids": [job["id"] for job in expired],
        }

    reclaimed_ids: list[str] = []
    for job in expired:
        if reclaim_job(store, job):
            reclaimed_ids.append(job["id"])

    requeued = 0
    if requeue and reclaimed_ids:
        requeued = _requeue_reclaimed(store, reclaimed_ids)

    return {
        "found": len(expired),
        "reclaimed": len(reclaimed_ids),
        "requeued": requeued,
        "job_ids": reclaimed_ids,
    }


def _requeue_reclaimed(store: ContentStore, job_ids: list[str]) -> int:
    """Put reclaimed jobs back on the queue.

    In ``background`` mode there is no standalone queue to push to; the job row is
    already back at ``queued`` and the next enqueue path picks it up, so this is a
    no-op rather than an error. A requeue failure is logged and left for the next
    sweep: the job stays ``queued`` and remains reclaimable.
    """
    if config.JOB_QUEUE_MODE != "rq":
        return 0

    from src.jobs.queue import requeue_job_with_delay

    requeued = 0
    for job_id in job_ids:
        try:
            requeue_job_with_delay(job_id, 0, store.database_url)
            requeued += 1
        except Exception as exc:
            log_event(
                logger,
                "job_reaper_requeue_failed",
                level=logging.ERROR,
                job_id=job_id,
                error=str(exc),
            )
    return requeued


async def run_reaper_loop(
    store: ContentStore,
    interval_seconds: int | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Sweep expired leases forever, until ``stop_event`` is set.

    Exceptions are swallowed per-iteration: a transient database error must not
    kill the recovery loop, or the very outage that stranded the jobs would also
    disable the mechanism that recovers them.
    """
    interval = interval_seconds or config.JOB_REAPER_INTERVAL_SECONDS
    while not (stop_event and stop_event.is_set()):
        try:
            result = reap_expired_leases(store, dry_run=False)
            if result["found"]:
                log_event(
                    logger,
                    "job_reaper_sweep_completed",
                    found=result["found"],
                    reclaimed=result["reclaimed"],
                    requeued=result["requeued"],
                )
        except Exception as exc:
            log_event(
                logger,
                "job_reaper_sweep_failed",
                level=logging.ERROR,
                error=str(exc),
            )

        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                continue
        await asyncio.sleep(interval)


def main() -> None:
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

    args = parser.parse_args()
    dry_run = not args.execute

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    store = ContentStore(database_url=config.DATABASE_URL, initialize_schema=False)
    try:
        if args.loop:
            if dry_run:
                parser.error("--loop requires --execute")
            asyncio.run(run_reaper_loop(store, interval_seconds=args.interval_seconds))
            return

        result = reap_expired_leases(store, dry_run=dry_run, limit=args.limit)
        mode = "DRY RUN" if dry_run else "EXECUTED"
        print(f"\n{mode} - Lease Reaper Results:")
        print(f"  Expired leases found: {result['found']}")
        print(f"  Reclaimed: {result['reclaimed']}")
        print(f"  Requeued: {result['requeued']}")
        if dry_run and result["found"]:
            print("\nNo jobs were reclaimed. Run with --execute to recover them.")
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
