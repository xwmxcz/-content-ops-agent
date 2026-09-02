"""HTTP request metrics middleware for Prometheus."""
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.utils import metrics


class MetricsMiddleware(BaseHTTPMiddleware):
    """Track HTTP request count and duration for Prometheus."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics for the /metrics endpoint itself to avoid recursion
        if request.url.path == "/api/metrics":
            return await call_next(request)

        start_time = time.time()
        method = request.method
        endpoint = request.url.path

        try:
            response = await call_next(request)
            status = response.status_code

            # Track metrics
            duration = time.time() - start_time
            metrics.http_requests_total.labels(
                method=method, endpoint=endpoint, status=status
            ).inc()
            metrics.http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

            return response
        except Exception as exc:
            # Track failed requests (500)
            duration = time.time() - start_time
            metrics.http_requests_total.labels(
                method=method, endpoint=endpoint, status=500
            ).inc()
            metrics.http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)
            raise
