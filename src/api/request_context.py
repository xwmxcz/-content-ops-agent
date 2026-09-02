"""Request correlation middleware for structured operational logs."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.utils.structured_logging import log_event


logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("x-request-id", "").strip()
        request_id = supplied[:128] if supplied else f"req_{uuid.uuid4().hex[:16]}"
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log_event(
                logger,
                "request_failed",
                level=logging.ERROR,
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                error_class=exc.__class__.__name__,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        response.headers["X-Request-ID"] = request_id
        log_event(
            logger,
            "request_complete",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return response
