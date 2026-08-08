"""Small auth helpers for the single-admin deployment mode."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.utils import config


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
    payload = {"sub": username, "iat": issued_at, "exp": expires_at}
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

    return payload


def get_request_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    scheme, _, value = auth_header.partition(" ")
    if scheme.lower() == "bearer" and value:
        return value.strip()
    return request.query_params.get("access_token")


def credentials_match(username: str, password: str) -> bool:
    return _safe_string_equal(username, config.AUTH_USERNAME) and _safe_string_equal(password, config.AUTH_PASSWORD)


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

        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})


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
