from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.api.dependencies import get_store
from src.utils import config


router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe: the process is up and serving. Kept dependency-free so it
    stays green even while the DB or Redis is briefly unreachable."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check() -> JSONResponse:
    """Readiness probe: verifies the backing services this process needs are
    reachable (DB always, Redis only in `rq` mode). Returns 503 when degraded so
    orchestrators can hold traffic. Errors are reported by exception class only,
    never the raw message, to avoid leaking connection strings or credentials."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        with get_store().engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - any failure means not-ready
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    if config.JOB_QUEUE_MODE == "rq":
        try:
            from redis import Redis

            Redis.from_url(config.REDIS_URL).ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc.__class__.__name__}"
            healthy = False

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
