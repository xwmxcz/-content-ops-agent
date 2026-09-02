from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from src.api.security import (
    create_access_token,
    create_resource_ticket,
    credentials_match,
    decode_access_token,
    get_request_token,
    is_auth_configured,
    RESOURCE_SESSION_COOKIE,
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


class ResourceTicketRequest(BaseModel):
    path: str


class ResourceTicketResponse(BaseModel):
    access_ticket: str
    expires_at: int


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


@router.post("/resource-ticket", response_model=ResourceTicketResponse)
def resource_ticket(payload: ResourceTicketRequest) -> ResourceTicketResponse:
    if config.APP_ENV == "production":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="URL resource tickets are disabled in production; use the HttpOnly resource session cookie",
        )
    if not config.AUTH_ENABLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authentication is disabled")
    try:
        ticket, expires_at = create_resource_ticket(config.AUTH_USERNAME, payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResourceTicketResponse(access_ticket=ticket, expires_at=expires_at)


@router.post("/login", response_model=AuthLoginResponse)
def login(payload: AuthLoginRequest, response: Response) -> AuthLoginResponse:
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
    response.set_cookie(
        key=RESOURCE_SESSION_COOKIE,
        value=token,
        max_age=max(expires_at - int(time.time()), 1),
        httponly=True,
        secure=config.APP_ENV == "production",
        samesite="strict",
        path="/api",
    )
    return AuthLoginResponse(
        access_token=token,
        expires_at=expires_at,
        username=config.AUTH_USERNAME,
        enabled=True,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(
        key=RESOURCE_SESSION_COOKIE,
        httponly=True,
        secure=config.APP_ENV == "production",
        samesite="strict",
        path="/api",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
