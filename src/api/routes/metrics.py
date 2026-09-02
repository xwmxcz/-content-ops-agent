"""Prometheus metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Response

from src.utils.metrics import get_metrics_text

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text format, or 503 if prometheus_client is not available.
    """
    metrics_text = get_metrics_text()
    if metrics_text is None:
        return Response(
            content="prometheus_client not installed\n",
            status_code=503,
            media_type="text/plain"
        )
    
    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )
