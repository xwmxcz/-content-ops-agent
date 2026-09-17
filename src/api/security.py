"""Signed, revocable database sessions and narrow browser-resource authentication."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import re
import time
from typing import Any

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.utils import config

RESOURCE_SESSION_COOKIE = "content_ops_resource_session"
PUBLIC_API_PATHS = {"/api/health", "/api/health/ready", "/api/auth/login", "/api/auth/register", "/api/auth/status"}
_TOKEN_VERSION = 2
_ID = re.compile(r"[0-9a-f]{32}")


def is_auth_configured() -> bool:
    return bool(config.AUTH_SECRET_KEY)


def create_access_token(user_id: str, session_id: str, expires_at: int | None = None) -> tuple[str, int]:
    expiry = expires_at if expires_at is not None else int(time.time()) + max(config.AUTH_TOKEN_EXPIRE_MINUTES, 1) * 60
    return _create_token(user_id, session_id, expiry, "access"), expiry


def _create_token(user_id: str, session_id: str, expires_at: int, token_use: str, **extra) -> str:
    if not is_auth_configured():
        raise RuntimeError("AUTH_SECRET_KEY is required")
    if not _ID.fullmatch(user_id) or not _ID.fullmatch(session_id):
        raise ValueError("Tokens require database user and session IDs")
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "v": _TOKEN_VERSION,
        "sub": user_id,
        "sid": session_id,
        "iat": int(time.time()),
        "exp": expires_at,
        "token_use": token_use,
        "iss": "content-ops-agent",
        "aud": "content-ops-api",
        **extra,
    }
    signing_input = f"{_json_b64(header)}.{_json_b64(payload)}"
    return f"{signing_input}.{_sign(signing_input)}"


def _decode_signed_payload(token: str | None) -> dict[str, Any] | None:
    if not token or not config.AUTH_SECRET_KEY or len(token) > 4096:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    signing_input = f"{parts[0]}.{parts[1]}"
    try:
        if not hmac.compare_digest(_sign(signing_input), parts[2]):
            return None
        header = _json_unb64(parts[0])
        payload = _json_unb64(parts[1])
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        return None
    if header != {"alg": "HS256", "typ": "JWT"} or not isinstance(payload, dict):
        return None
    if (
        payload.get("v") != _TOKEN_VERSION
        or payload.get("iss") != "content-ops-agent"
        or payload.get("aud") != "content-ops-api"
    ):
        return None
    if not isinstance(payload.get("sub"), str) or not _ID.fullmatch(payload["sub"]):
        return None
    if not isinstance(payload.get("sid"), str) or not _ID.fullmatch(payload["sid"]):
        return None
    expires, issued = payload.get("exp"), payload.get("iat")
    if type(expires) is not int or type(issued) is not int:
        return None
    if expires <= int(time.time()) or expires <= issued or issued > time.time() + 60:
        return None
    return payload


def decode_access_token(token: str | None) -> dict[str, Any] | None:
    payload = _decode_signed_payload(token)
    return payload if payload and payload.get("token_use") == "access" else None


def create_resource_ticket(user_id: str, session_id: str, path: str) -> tuple[str, int]:
    if not is_ticket_path(path):
        raise ValueError("Resource tickets are restricted to approved stream or media paths")
    if path.startswith("/api/media/"):
        duration = max(30, min(config.AUTH_MEDIA_TICKET_SECONDS, 900))
    else:
        duration = max(5, min(config.AUTH_RESOURCE_TICKET_SECONDS, 120))
    expiry = int(time.time()) + duration
    return _create_token(user_id, session_id, expiry, "resource", path=path), expiry


def decode_resource_ticket(ticket: str | None, path: str) -> dict[str, Any] | None:
    payload = _decode_signed_payload(ticket)
    return payload if payload and payload.get("token_use") == "resource" and payload.get("path") == path else None


def is_ticket_path(path: str) -> bool:
    return bool(
        re.fullmatch(r"/api/agent/runs/[A-Za-z0-9_-]{1,80}/stream", path)
        or re.fullmatch(r"/api/media/[0-9]{1,20}/file", path)
    )


def get_request_token(request: Request) -> str | None:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value else None


def authenticate_request(request: Request) -> dict | None:
    """Resolve every credential through the same live DB-session check."""
    from src.api.dependencies import get_account_store

    payload = decode_access_token(get_request_token(request))
    if payload is None and request.method in {"GET", "HEAD"} and is_ticket_path(request.url.path):
        payload = decode_access_token(request.cookies.get(RESOURCE_SESSION_COOKIE))
        if payload is None and config.APP_ENV in {"development", "test"}:
            payload = decode_resource_ticket(request.query_params.get("access_ticket"), request.url.path)
    if payload is None:
        return None
    return get_account_store().resolve_session(payload["sid"], payload["sub"])


class HttpsEnforcementMiddleware(BaseHTTPMiddleware):
    """Reject production API traffic unless TLS was preserved by the proxy."""

    async def dispatch(self, request: Request, call_next):
        if (
            not config.ENFORCE_HTTPS
            or request.method == "OPTIONS"
            or not request.url.path.startswith("/api")
            or request.url.path in {"/api/health", "/api/health/ready"}
        ):
            return await call_next(request)
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
        client_host = request.client.host if request.client else ""
        if request.url.scheme == "https" or (forwarded_proto == "https" and _is_trusted_proxy(client_host)):
            return await call_next(request)
        return JSONResponse(status_code=426, content={"detail": "HTTPS is required"})


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.method == "OPTIONS"
            or not request.url.path.startswith("/api")
            or request.url.path in PUBLIC_API_PATHS
        ):
            response = await call_next(request)
        else:
            if not is_auth_configured():
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Server signing key is not configured"},
                    headers={"Cache-Control": "no-store"},
                )
            user = await run_in_threadpool(authenticate_request, request)
            if user is None:
                return JSONResponse(
                    status_code=401, content={"detail": "请先登录"}, headers={"Cache-Control": "no-store"}
                )
            request.state.user = user
            response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response


def _is_trusted_proxy(host: str) -> bool:
    """Return whether forwarding headers from ``host`` are an explicit trust boundary."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    for value in config.TRUSTED_PROXY_CIDRS:
        try:
            if address in ipaddress.ip_network(value, strict=False):
                return True
        except ValueError:
            # Runtime validation rejects invalid production values. Treat any
            # invalid entry as non-trusted here for defense in depth.
            continue
    return False


def _json_b64(value: dict[str, Any]) -> str:
    data = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64encode(data)


def _json_unb64(value: str) -> Any:
    return json.loads(_b64decode(value).decode("utf-8"))


def _sign(value: str) -> str:
    digest = hmac.new(config.AUTH_SECRET_KEY.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
