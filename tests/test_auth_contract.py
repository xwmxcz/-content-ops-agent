"""Exercise real account/session HTTP contracts against disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_system_store
from src.api.main import app
from src.api.passwords import verify_password
from src.api.security import RESOURCE_SESSION_COOKIE, create_access_token, decode_access_token
from src.storage.content_store import AuthSession, User
from src.utils import config

pytestmark = pytest.mark.real_auth
PASSWORD = "Local-test-password-28!"


def register(client, username="account_a"):
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD})
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def bearer(session):
    return {"Authorization": f"Bearer {session['access_token']}"}


def make_run(session, run_id="run_auth"):
    owned = get_system_store().for_user(session["user"]["id"])
    owned.create_run(run_id, "private", "blog", "casual")
    owned.transition_run_and_append_event(
        run_id, expected_statuses={"running"}, new_status="completed", event_type="run_complete", payload={"ok": True}
    )
    return f"/api/agent/runs/{run_id}/stream"


def test_anonymous_status_and_public_health_are_available_but_api_is_protected(store):
    with TestClient(app) as client:
        assert client.get("/api/auth/status").json() == {"authenticated": False, "user": None}
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/content").status_code == 401


def test_registration_normalizes_username_hashes_password_and_logs_in(store):
    with TestClient(app) as client:
        created = register(client, "  Alice_01  ")
        assert created["user"]["username"] == "alice_01"
        assert set(created["user"]) == {"id", "username"}
        assert created["token_type"] == "bearer"
        assert created["expires_at"] > datetime.now(timezone.utc).timestamp()
        assert client.get("/api/content", headers=bearer(created)).json() == []
        assert client.get("/api/auth/status", headers=bearer(created)).json() == {
            "authenticated": True,
            "user": created["user"],
        }
        with get_system_store()._get_session() as db:
            user = db.get(User, created["user"]["id"])
            assert user.password_hash.startswith("$argon2id$")
            assert user.password_hash != PASSWORD
            assert verify_password(user.password_hash, PASSWORD)
        login = client.post("/api/auth/login", json={"username": " ALICE_01 ", "password": PASSWORD})
        assert login.status_code == 200
        assert login.json()["user"] == created["user"]
        assert login.json()["access_token"] != created["access_token"]


def test_registration_rejects_normalized_duplicate_names(store):
    with TestClient(app) as client:
        register(client, "alice")
        response = client.post("/api/auth/register", json={"username": " ALICE ", "password": PASSWORD})
        assert response.status_code == 409


def test_simultaneous_registration_has_one_winner(store):
    def attempt(_):
        with TestClient(app) as client:
            return client.post("/api/auth/register", json={"username": "race_user", "password": PASSWORD}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, range(2))) == [201, 409]


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ab", "password": PASSWORD},
        {"username": "a" * 33, "password": PASSWORD},
        {"username": "contains space", "password": PASSWORD},
        {"username": "../outside", "password": PASSWORD},
        {"username": "valid_user", "password": "short"},
        {"username": "valid_user", "password": "x" * 129},
        {"username": "valid_user", "password": " " * 12},
        {"username": "valid_user", "password": "x" * 12 + "\x00"},
        {"username": "valid_user", "password": PASSWORD, "user_id": "a" * 32},
    ],
)
def test_invalid_registration_inputs_fail_before_creating_accounts(store, payload):
    with TestClient(app) as client:
        assert client.post("/api/auth/register", json=payload).status_code == 422
    with get_system_store()._get_session() as db:
        assert db.query(User).count() == 1


def test_bad_password_unknown_and_disabled_accounts_have_same_login_response(store):
    with TestClient(app) as client:
        created = register(client)
        bad_password = client.post("/api/auth/login", json={"username": "account_a", "password": "wrong"})
        unknown = client.post("/api/auth/login", json={"username": "unknown", "password": PASSWORD})
        with get_system_store()._get_session() as db:
            db.get(User, created["user"]["id"]).is_active = False
            db.commit()
        disabled = client.post("/api/auth/login", json={"username": "account_a", "password": PASSWORD})
        for response in (bad_password, unknown, disabled):
            assert response.status_code == 401
            assert response.json() == {"detail": "用户名或密码错误"}
        assert client.get("/api/content", headers=bearer(created)).status_code == 401


def test_migrated_legacy_workspace_is_not_claimed_by_registration(store):
    from alembic import command
    from sqlalchemy import text

    from src.models import ContentType, GeneratedContent
    from src.storage.content_store import Base
    from src.storage.schema import alembic_config
    from src.storage.tenancy import LEGACY_USER_ID

    Base.metadata.drop_all(store.engine)
    with store.engine.begin() as db:
        db.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(alembic_config(store.database_url), "head")
    legacy = get_system_store().for_user(LEGACY_USER_ID)
    legacy_id = legacy.save_content(GeneratedContent(content="legacy private data", content_type=ContentType.BLOG))
    with TestClient(app) as client:
        collision = client.post("/api/auth/register", json={"username": "__legacy_workspace__", "password": PASSWORD})
        assert collision.status_code == 409
        assert (
            client.post("/api/auth/login", json={"username": "__legacy_workspace__", "password": PASSWORD}).status_code
            == 401
        )
        created = register(client, "first_public_user")
        assert created["user"]["id"] != LEGACY_USER_ID
        assert client.get("/api/content", headers=bearer(created)).json() == []
        assert client.get(f"/api/content/{legacy_id}", headers=bearer(created)).status_code == 404


@pytest.mark.parametrize("route,limit", [("register", 5), ("login", 15)])
def test_authentication_rate_limits_are_enforced_in_database(store, route, limit):
    with TestClient(app) as client:
        for index in range(limit):
            response = client.post(f"/api/auth/{route}", json={"username": f"attempt_{index}", "password": PASSWORD})
            assert response.status_code == (201 if route == "register" else 401)
        response = client.post(
            f"/api/auth/{route}",
            json={"username": "overflow", "password": PASSWORD},
            headers={"X-Forwarded-For": "different-peer"},
        )
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"


def test_resource_cookie_never_authorizes_regular_api_or_general_url_bearer(store):
    with TestClient(app) as client:
        created = register(client)
        assert client.get("/api/content").status_code == 401
        assert client.post("/api/auth/logout").status_code == 401
        token = created["access_token"]
        assert client.get(f"/api/content?access_token={token}").status_code == 401
        path = make_run(created)
        assert client.get(path).status_code == 200
        client.cookies.clear()
        assert client.get(f"{path}?access_token={token}").status_code == 401
        assert client.get(f"{path}?access_ticket={token}").status_code == 401


def test_logout_revokes_bearer_resource_cookie_and_resource_ticket(store):
    with TestClient(app) as client:
        created = register(client)
        old_cookie = client.cookies.get(RESOURCE_SESSION_COOKIE)
        path = make_run(created)
        ticket = client.post("/api/auth/resource-ticket", headers=bearer(created), json={"path": path})
        assert ticket.status_code == 200
        assert client.get(path).status_code == 200
        assert client.post("/api/auth/logout", headers=bearer(created)).status_code == 204
        assert client.cookies.get(RESOURCE_SESSION_COOKIE) is None
        assert client.get("/api/content", headers=bearer(created)).status_code == 401
        assert client.get(path, headers={"Cookie": f"{RESOURCE_SESSION_COOKIE}={old_cookie}"}).status_code == 401
        assert client.get(path, params={"access_ticket": ticket.json()["access_ticket"]}).status_code == 401
        assert client.get("/api/auth/status", headers=bearer(created)).json() == {"authenticated": False, "user": None}


def test_logout_only_revokes_the_current_session(store):
    with TestClient(app) as client:
        first = register(client)
        second = client.post("/api/auth/login", json={"username": "account_a", "password": PASSWORD}).json()
        assert client.post("/api/auth/logout", headers=bearer(first)).status_code == 204
        assert client.get("/api/content", headers=bearer(first)).status_code == 401
        assert client.get("/api/content", headers=bearer(second)).status_code == 200


def test_database_expiry_rejects_a_still_signed_bearer(store):
    with TestClient(app) as client:
        created = register(client)
        claims = decode_access_token(created["access_token"])
        with get_system_store()._get_session() as db:
            db.get(AuthSession, claims["sid"]).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        assert decode_access_token(created["access_token"]) is not None
        assert client.get("/api/content", headers=bearer(created)).status_code == 401


def test_cross_account_session_substitution_and_old_admin_tokens_are_rejected(store):
    import base64
    import hashlib
    import hmac
    import json
    import time

    with TestClient(app) as client:
        first = register(client, "first_owner")
        second = register(client, "second_owner")
        other_session_id = decode_access_token(second["access_token"])["sid"]
        forged, _ = create_access_token(first["user"]["id"], other_session_id)
        assert client.get("/api/content", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"sub": "admin", "iat": int(time.time()), "exp": int(time.time()) + 600}).encode()
            )
            .decode()
            .rstrip("=")
        )
        message = f"{header}.{payload}"
        digest = hmac.new(config.AUTH_SECRET_KEY.encode(), message.encode(), hashlib.sha256).digest()
        legacy = message + "." + base64.urlsafe_b64encode(digest).decode().rstrip("=")
        assert client.get("/api/content", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401


def test_production_cookie_is_secure_and_url_ticket_issuance_is_gone(store, monkeypatch):
    with TestClient(app, base_url="https://testserver") as client:
        monkeypatch.setattr(config, "APP_ENV", "production")
        response = client.post("/api/auth/register", json={"username": "secure_user", "password": PASSWORD})
        assert response.status_code == 201
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie and "Path=/api" in cookie
        created = response.json()
        path = make_run(created)
        assert "event: run_complete" in client.get(path).text
        assert client.post("/api/auth/resource-ticket", headers=bearer(created), json={"path": path}).status_code == 410


def test_missing_signing_key_fails_closed(store, monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(config, "AUTH_SECRET_KEY", "")
        payload = {"username": "valid_user", "password": PASSWORD}
        assert client.post("/api/auth/register", json=payload).status_code == 503
        assert client.post("/api/auth/login", json=payload).status_code == 503
        assert client.get("/api/content").status_code == 503
