"""Small auth helpers for the single-admin deployment mode."""
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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.utils import config


RESOURCE_SESSION_COOKIE = "content_ops_resource_session"


PUBLIC_API_PATHS = {
    "/api/health",
    "/api/health/ready",
    "/api/auth/login",
    "/api/auth/status",
}


def is_auth_configured() -> bool:
    if not config.AUTH_ENABLED:
        return True
    return bool(config.AUTH_PASSWORD and config.AUTH_SECRET_KEY)


def create_access_token(username: str) -> tuple[str, int]:
    if not is_auth_configured():
        raise RuntimeError("Authentication is enabled but AUTH_PASSWORD or AUTH_SECRET_KEY is missing")

    issued_at = int(time.time())
    expires_at = issued_at + max(config.AUTH_TOKEN_EXPIRE_MINUTES, 1) * 60
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": username, "iat": issued_at, "exp": expires_at, "token_use": "access"}
    signing_input = f"{_json_b64(header)}.{_json_b64(payload)}"
    return f"{signing_input}.{_sign(signing_input)}", expires_at


def decode_access_token(token: str | None) -> dict[str, Any] | None:
    if not token or not config.AUTH_SECRET_KEY:
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    signing_input = f"{parts[0]}.{parts[1]}"
    expected_signature = _sign(signing_input)
    if not hmac.compare_digest(expected_signature, parts[2]):
        return None

    try:
        payload = _json_unb64(parts[1])
    except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None

    subject = payload.get("sub")
    if subject != config.AUTH_USERNAME:
        return None
    # Tokens issued before token_use was introduced remain valid until their
    # normal expiry, but resource tickets can never be used as API bearer tokens.
    if payload.get("token_use", "access") != "access":
        return None

    return payload


def create_resource_ticket(username: str, path: str) -> tuple[str, int]:
    if not is_auth_configured():
        raise RuntimeError("Authentication is enabled but AUTH_PASSWORD or AUTH_SECRET_KEY is missing")
    if not is_ticket_path(path):
        raise ValueError("Resource tickets are restricted to approved stream or media paths")
    issued_at = int(time.time())
    if re.fullmatch(r"/api/media/[0-9]{1,20}/file", path):
        ttl_seconds = max(30, min(config.AUTH_MEDIA_TICKET_SECONDS, 900))
    else:
        ttl_seconds = max(5, min(config.AUTH_RESOURCE_TICKET_SECONDS, 120))
    expires_at = issued_at + ttl_seconds
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "iat": issued_at,
        "exp": expires_at,
        "token_use": "resource",
        "path": path,
    }
    signing_input = f"{_json_b64(header)}.{_json_b64(payload)}"
    return f"{signing_input}.{_sign(signing_input)}", expires_at


def decode_resource_ticket(ticket: str | None, path: str) -> dict[str, Any] | None:
    payload = _decode_signed_payload(ticket)
    if not payload:
        return None
    if payload.get("token_use") != "resource" or payload.get("path") != path:
        return None
    if payload.get("sub") != config.AUTH_USERNAME:
        return None
    return payload


def is_ticket_path(path: str) -> bool:
    return bool(
        re.fullmatch(r"/api/agent/runs/[A-Za-z0-9_-]{1,80}/stream", path)
        or re.fullmatch(r"/api/media/[0-9]{1,20}/file", path)
    )


def get_request_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    scheme, _, value = auth_header.partition(" ")
    if scheme.lower() == "bearer" and value:
        return value.strip()
    return None


def credentials_match(username: str, password: str) -> bool:
    return _safe_string_equal(username, config.AUTH_USERNAME) and _safe_string_equal(password, config.AUTH_PASSWORD)


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
        if request.url.scheme == "https" or (
            forwarded_proto == "https" and _is_trusted_proxy(client_host)
        ):
            return await call_next(request)
        return JSONResponse(status_code=426, content={"detail": "HTTPS is required"})


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            not config.AUTH_ENABLED
            or request.method == "OPTIONS"
            or not request.url.path.startswith("/api")
            or request.url.path in PUBLIC_API_PATHS
        ):
            return await call_next(request)

        if not is_auth_configured():
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication is enabled but server auth settings are incomplete"},
            )

        if decode_access_token(get_request_token(request)):
            return await call_next(request)

        # Native EventSource and browser media elements use an HttpOnly session
        # cookie, accepted only for narrow read-only resource paths. This avoids
        # bearer material in URLs and never authorizes normal API writes.
        if is_ticket_path(request.url.path):
            cookie_token = request.cookies.get(RESOURCE_SESSION_COOKIE)
            if decode_access_token(cookie_token):
                return await call_next(request)
            # Explicit development/test compatibility only. Production rejects
            # every access_ticket query credential to prevent log leaks/replay.
            if config.APP_ENV in {"development", "test"}:
                resource_ticket = request.query_params.get("access_ticket")
                if decode_resource_ticket(resource_ticket, request.url.path):
                    return await call_next(request)

        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})


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


def _decode_signed_payload(token: str | None) -> dict[str, Any] | None:
    if not token or not config.AUTH_SECRET_KEY:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    signing_input = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_sign(signing_input), parts[2]):
        return None
    try:
        payload = _json_unb64(parts[1])
    except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None
    return payload


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


def _safe_string_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
