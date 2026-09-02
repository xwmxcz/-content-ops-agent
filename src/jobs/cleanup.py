"""Job cleanup mechanism for archiving old completed and failed jobs.

Usage:
    python -m src.jobs.cleanup --dry-run
    python -m src.jobs.cleanup --execute
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta

from src.storage import ContentStore
from src.utils import config
from src.utils.structured_logging import log_event

logger = logging.getLogger(__name__)


def cleanup_old_jobs(
    store: ContentStore,
    completed_retention_days: int = 30,
    failed_retention_days: int = 7,
    dry_run: bool = True,
) -> dict[str, int]:
    """Clean up old completed and failed jobs.
    
    Args:
        store: ContentStore instance
        completed_retention_days: Days to keep completed jobs (default: 30)
        failed_retention_days: Days to keep failed jobs (default: 7)
        dry_run: If True, only count jobs without deleting
        
    Returns:
        Dict with counts: {"completed": N, "failed": M, "total": N+M}
    """
    now = datetime.now()
    completed_cutoff = now - timedelta(days=completed_retention_days)
    failed_cutoff = now - timedelta(days=failed_retention_days)
    
    session = store._get_session()
    try:
        from src.storage.content_store import Job
        
        # Find old completed jobs
        completed_jobs = (
            session.query(Job)
            .filter(
                Job.status == "completed",
                Job.updated_at < completed_cutoff,
            )
            .all()
        )
        
        # Find old failed jobs (permanently failed, not scheduled for retry)
        failed_jobs = (
            session.query(Job)
            .filter(
                Job.status == "failed",
                Job.next_retry_at.is_(None),  # Not scheduled for retry
                Job.updated_at < failed_cutoff,
            )
            .all()
        )
        
        completed_count = len(completed_jobs)
        failed_count = len(failed_jobs)
        total_count = completed_count + failed_count
        
        log_event(
            logger,
            "job_cleanup_started",
            dry_run=dry_run,
            completed_count=completed_count,
            failed_count=failed_count,
            total_count=total_count,
            completed_cutoff=completed_cutoff.isoformat(),
            failed_cutoff=failed_cutoff.isoformat(),
        )
        
        if not dry_run:
            # Delete the jobs
            for job in completed_jobs + failed_jobs:
                session.delete(job)
            
            session.commit()
            
            log_event(
                logger,
                "job_cleanup_completed",
                deleted_count=total_count,
            )
        else:
            log_event(
                logger,
                "job_cleanup_dry_run",
                would_delete_count=total_count,
            )
        
        return {
            "completed": completed_count,
            "failed": failed_count,
            "total": total_count,
        }
    
    except Exception as exc:
        session.rollback()
        log_event(
            logger,
            "job_cleanup_failed",
            level=logging.ERROR,
            error=str(exc),
        )
        raise
    finally:
        session.close()


def main() -> None:
    """CLI entry point for job cleanup."""
    parser = argparse.ArgumentParser(description="Clean up old completed and failed jobs")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Count jobs without deleting (default: true if no --execute)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually delete jobs (use with caution)",
    )
    parser.add_argument(
        "--completed-retention-days",
        type=int,
        default=30,
        help="Days to keep completed jobs (default: 30)",
    )
    parser.add_argument(
        "--failed-retention-days",
        type=int,
        default=7,
        help="Days to keep failed jobs (default: 7)",
    )
    
    args = parser.parse_args()
    
    # Default to dry-run unless --execute is specified
    dry_run = not args.execute
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    store = ContentStore(database_url=config.DATABASE_URL, initialize_schema=False)
    
    try:
        result = cleanup_old_jobs(
            store,
            completed_retention_days=args.completed_retention_days,
            failed_retention_days=args.failed_retention_days,
            dry_run=dry_run,
        )
        
        mode = "DRY RUN" if dry_run else "EXECUTED"
        print(f"\n{mode} - Job Cleanup Results:")
        print(f"  Completed jobs: {result['completed']}")
        print(f"  Failed jobs: {result['failed']}")
        print(f"  Total: {result['total']}")
        
        if dry_run:
            print("\nNo jobs were deleted. Run with --execute to delete.")
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
