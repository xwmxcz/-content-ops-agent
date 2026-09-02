"""Minimal JSON logging with request correlation and no payload logging."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_FIELDS or key.startswith("_"):
                continue
            payload[key] = _json_safe(value)
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    normalized = getattr(logging, (level or "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(normalized)


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    # Callers pass identifiers and aggregate metadata only. Prompts, tool output,
    # tokens, credentials, and connection strings must never be included.
    logger.log(level, event, extra={"event": event, **fields})


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


# ============================================================================
# Event-Specific Logging Helpers (Phase 2)
# ============================================================================

def log_idempotency_event(
    logger: logging.Logger,
    outcome: str,
    scope: str,
    idempotency_key: str,
    *,
    record_id: int | None = None,
    args_hash: str | None = None,
    conflict: bool = False
) -> None:
    """
    Log idempotency events: claim, replay, conflict.
    
    Args:
        outcome: "claimed", "replay", or "conflict"
        scope: idempotency scope (e.g., "generate_content")
        idempotency_key: the client-provided key
        record_id: database record ID (if applicable)
        args_hash: hash of arguments (for conflict detection)
        conflict: whether this is a conflict/tampered request
    """
    event = f"idempotency_{outcome}"
    log_event(
        logger,
        event,
        scope=scope,
        idempotency_key=idempotency_key,
        record_id=record_id,
        args_hash=args_hash,
        conflict=conflict
    )


def log_job_event(
    logger: logging.Logger,
    event: str,
    job_id: str,
    job_type: str,
    *,
    error_type: str | None = None,
    retry_count: int | None = None,
    max_retries: int | None = None,
    next_retry_at: str | None = None
) -> None:
    """
    Log job lifecycle events: retry_scheduled, failed_permanently, completed.
    
    Args:
        event: "job_retry_scheduled", "job_failed_permanently", "job_completed"
        job_id: job identifier
        job_type: type of job (e.g., "publication")
        error_type: "transient" or "permanent" (for failures)
        retry_count: current retry attempt number
        max_retries: maximum allowed retries
        next_retry_at: ISO timestamp of next retry
    """
    log_event(
        logger,
        event,
        job_id=job_id,
        job_type=job_type,
        error_type=error_type,
        retry_count=retry_count,
        max_retries=max_retries,
        next_retry_at=next_retry_at
    )


def log_capability_event(
    logger: logging.Logger,
    event: str,
    action_id: str,
    tool: str,
    *,
    thread_id: str | None = None,
    consumed: bool = False,
    expired: bool = False,
    tampered: bool = False
) -> None:
    """
    Log capability lifecycle events: proposed, consumed, expired, tampered.
    
    Args:
        event: "capability_proposed", "capability_consumed", "capability_expired", "capability_tampered"
        action_id: unique capability/action identifier
        tool: tool name (e.g., "generate_content", "schedule_publication")
        thread_id: conversation thread ID
        consumed: whether this capability was consumed
        expired: whether this capability expired
        tampered: whether this capability was tampered with
    """
    log_event(
        logger,
        event,
        action_id=action_id,
        tool=tool,
        thread_id=thread_id,
        consumed=consumed,
        expired=expired,
        tampered=tampered
    )
