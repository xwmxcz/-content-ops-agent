from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from src.api.security import (
    create_access_token,
    credentials_match,
    decode_access_token,
    get_request_token,
    is_auth_configured,
)
from src.utils import config


router = APIRouter()


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int | None = None
    username: str
    enabled: bool


class AuthStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    authenticated: bool
    username: str | None = None


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(request: Request) -> AuthStatusResponse:
    payload = decode_access_token(get_request_token(request))
    authenticated = not config.AUTH_ENABLED or payload is not None
    return AuthStatusResponse(
        enabled=config.AUTH_ENABLED,
        configured=is_auth_configured(),
        authenticated=authenticated,
        username=payload.get("sub") if payload else None,
    )


@router.post("/login", response_model=AuthLoginResponse)
def login(payload: AuthLoginRequest) -> AuthLoginResponse:
    if not config.AUTH_ENABLED:
        return AuthLoginResponse(
            access_token="",
            expires_at=None,
            username=payload.username,
            enabled=False,
        )

    if not is_auth_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is enabled but AUTH_PASSWORD or AUTH_SECRET_KEY is missing",
        )

    if not credentials_match(payload.username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token, expires_at = create_access_token(config.AUTH_USERNAME)
    return AuthLoginResponse(
        access_token=token,
        expires_at=expires_at,
        username=config.AUTH_USERNAME,
        enabled=True,
    )
