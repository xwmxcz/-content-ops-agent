"""Prometheus metrics for observability.

Gracefully degrades if prometheus_client is not installed.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# Try to import prometheus_client, gracefully degrade if not available
try:
    from prometheus_client import Counter as _Counter
    from prometheus_client import Histogram as _Histogram
    from prometheus_client import REGISTRY, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.warning("prometheus_client not installed, metrics will be no-ops")
    PROMETHEUS_AVAILABLE = False
    REGISTRY = None
    generate_latest = None
    _Counter = None
    _Histogram = None


class NoOpMetric:
    """No-op metric when prometheus_client is not available."""
    def inc(self, amount: float = 1, **labels) -> None:
        pass
    
    def observe(self, amount: float, **labels) -> None:
        pass
    
    def labels(self, **labels):
        return self


def _create_counter(name: str, documentation: str, labelnames: list[str] | None = None) -> Counter | NoOpMetric:
    """Create a Counter metric or no-op if prometheus unavailable."""
    if not PROMETHEUS_AVAILABLE:
        return NoOpMetric()
    return _Counter(name, documentation, labelnames or [])


def _create_histogram(name: str, documentation: str, labelnames: list[str] | None = None, 
                      buckets: tuple = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)) -> Histogram | NoOpMetric:
    """Create a Histogram metric or no-op if prometheus unavailable."""
    if not PROMETHEUS_AVAILABLE:
        return NoOpMetric()
    return _Histogram(name, documentation, labelnames or [], buckets=buckets)


# ============================================================================
# Idempotency Metrics
# ============================================================================

idempotency_requests_total = _create_counter(
    "idempotency_requests_total",
    "Total idempotency requests by scope and outcome",
    labelnames=["scope", "outcome"]
)

idempotency_replay_rate = _create_counter(
    "idempotency_replays_total",
    "Total replay requests (avoided duplicate work)",
    labelnames=["scope"]
)

idempotency_conflicts_total = _create_counter(
    "idempotency_conflicts_total",
    "Total idempotency conflicts (tampered requests)",
    labelnames=["scope"]
)

# ============================================================================
# Job Retry Metrics
# ============================================================================

job_retry_attempts_total = _create_counter(
    "job_retry_attempts_total",
    "Total job retry attempts by error type",
    labelnames=["error_type", "job_type"]
)

job_retry_exhausted_total = _create_counter(
    "job_retry_exhausted_total",
    "Total jobs that exhausted max retries",
    labelnames=["job_type"]
)

job_failures_total = _create_counter(
    "job_failures_total",
    "Total permanent job failures by error type",
    labelnames=["error_type", "job_type"]
)

job_completions_total = _create_counter(
    "job_completions_total",
    "Total successful job completions",
    labelnames=["job_type"]
)

# ============================================================================
# Job Lease and Checkpoint Metrics (P1-04)
# ============================================================================

job_lease_acquired_total = _create_counter(
    "job_lease_acquired_total",
    "Total job leases acquired by workers",
    labelnames=["job_type"]
)

job_lease_conflicts_total = _create_counter(
    "job_lease_conflicts_total",
    "Total lease acquisitions refused because another worker held a live lease",
    labelnames=["job_type"]
)

job_lease_lost_total = _create_counter(
    "job_lease_lost_total",
    "Total heartbeats that found the lease no longer owned by this worker",
    labelnames=["job_type"]
)

job_lease_reclaimed_total = _create_counter(
    "job_lease_reclaimed_total",
    "Total expired-lease jobs requeued by the reaper",
    labelnames=["job_type"]
)

job_checkpoints_saved_total = _create_counter(
    "job_checkpoints_saved_total",
    "Total completed run-step checkpoints persisted",
    labelnames=["step_name"]
)

job_cancellations_total = _create_counter(
    "job_cancellations_total",
    "Total jobs that observed a cancellation request while running",
    labelnames=["job_type"]
)

# ============================================================================
# Capability Metrics
# ============================================================================

capability_proposals_total = _create_counter(
    "capability_proposals_total",
    "Total capability proposals by tool",
    labelnames=["tool"]
)

capability_consumed_total = _create_counter(
    "capability_consumed_total",
    "Total capabilities consumed by tool",
    labelnames=["tool"]
)

capability_expired_total = _create_counter(
    "capability_expired_total",
    "Total expired capabilities",
    labelnames=["tool"]
)

capability_tampered_total = _create_counter(
    "capability_tampered_total",
    "Total tampered capability attempts",
    labelnames=["tool"]
)

# ============================================================================
# Publication Metrics
# ============================================================================

publication_requests_total = _create_counter(
    "publication_requests_total",
    "Total publication requests by platform and status",
    labelnames=["platform", "status"]
)

publication_duration_seconds = _create_histogram(
    "publication_duration_seconds",
    "Publication request duration in seconds",
    labelnames=["platform"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
)

# ============================================================================
# HTTP Metrics
# ============================================================================

http_requests_total = _create_counter(
    "http_requests_total",
    "Total HTTP requests by method, endpoint, and status",
    labelnames=["method", "endpoint", "status"]
)

http_request_duration_seconds = _create_histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)


def get_metrics_text() -> bytes | None:
    """Get Prometheus metrics in text format, or None if unavailable."""
    if not PROMETHEUS_AVAILABLE or generate_latest is None:
        return None
    return generate_latest(REGISTRY)
