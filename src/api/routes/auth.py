"""Database-backed registration, login, and revocable user sessions."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from src.api.dependencies import get_account_store, get_current_user, get_store
from src.api.passwords import DUMMY_PASSWORD_HASH, hash_password, verify_password
from src.api.schemas.auth import AuthStatusResponse, LoginRequest, PublicUser, RegisterRequest, SessionResponse
from src.api.security import (
    RESOURCE_SESSION_COOKIE,
    authenticate_request,
    create_access_token,
    create_resource_ticket,
    is_auth_configured,
)
from src.storage import ContentStore
from src.storage.account_store import AccountStore, UsernameTaken
from src.utils import config

router = APIRouter()


def _throttle(accounts: AccountStore, request: Request, scope: str, limit: int) -> None:
    # Use the actual peer, never untrusted forwarding headers. Deployments may
    # additionally enforce per-client limits at their trusted reverse proxy.
    peer = request.client.host if request.client else "unknown"
    if not accounts.check_rate_limit(scope, peer, limit=limit, seconds=60):
        raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试", headers={"Retry-After": "60"})


def _session_response(user: dict, accounts: AccountStore, response: Response) -> SessionResponse:
    session_id, expires_at = accounts.create_session(user["id"], config.AUTH_TOKEN_EXPIRE_MINUTES)
    token, _ = create_access_token(user["id"], session_id, expires_at)
    response.set_cookie(
        key=RESOURCE_SESSION_COOKIE, value=token,
        max_age=max(expires_at - int(time.time()), 1), httponly=True,
        secure=config.APP_ENV == "production", samesite="strict", path="/api",
    )
    return SessionResponse(access_token=token, expires_at=expires_at, user=PublicUser(**user))


def _require_signing_key() -> None:
    if not is_auth_configured():
        raise HTTPException(status_code=503, detail="服务端签名密钥尚未配置")


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(request: Request) -> AuthStatusResponse:
    user = authenticate_request(request)
    return AuthStatusResponse(authenticated=user is not None, user=PublicUser(**user) if user else None)


@router.post("/register", response_model=SessionResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response,
             accounts: AccountStore = Depends(get_account_store)) -> SessionResponse:
    _require_signing_key()
    _throttle(accounts, request, "register", 5)
    try:
        user = accounts.create_user(payload.username, hash_password(payload.password))
    except UsernameTaken as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _session_response(user, accounts, response)


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, request: Request, response: Response,
          accounts: AccountStore = Depends(get_account_store)) -> SessionResponse:
    _require_signing_key()
    _throttle(accounts, request, "login", 15)
    user = accounts.get_user_by_username(payload.username)
    valid = verify_password(user["password_hash"] if user and user["is_active"] else DUMMY_PASSWORD_HASH, payload.password)
    if not user or not valid or not user["is_active"]:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return _session_response(user, accounts, response)


class ResourceTicketRequest(BaseModel):
    path: str


@router.post("/resource-ticket")
def resource_ticket(payload: ResourceTicketRequest, user: dict = Depends(get_current_user),
                    store: ContentStore = Depends(get_store)) -> dict:
    if config.APP_ENV == "production":
        raise HTTPException(status_code=410, detail="Use the HttpOnly resource session cookie")
    try:
        token, expiry = create_resource_ticket(user["id"], user["session_id"], payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parts = payload.path.split("/")
    owned = store.get_media_asset(int(parts[3])) if parts[2] == "media" else store.get_run(parts[4])
    if not owned:
        raise HTTPException(status_code=404, detail="Resource not found")
    return {"access_ticket": token, "expires_at": expiry}


@router.post("/logout", status_code=204)
def logout(response: Response, user: dict = Depends(get_current_user),
           accounts: AccountStore = Depends(get_account_store)) -> Response:
    accounts.revoke_session(user["session_id"], user["id"])
    response.delete_cookie(RESOURCE_SESSION_COOKIE, httponly=True,
                           secure=config.APP_ENV == "production", samesite="strict", path="/api")
    response.status_code = 204
    return response
