from fastapi.testclient import TestClient

from src.api.main import app
from src.utils import config


def enable_auth(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(config, "AUTH_PASSWORD", "secret-password")
    monkeypatch.setattr(config, "AUTH_SECRET_KEY", "test-secret-key-with-enough-entropy")
    monkeypatch.setattr(config, "AUTH_TOKEN_EXPIRE_MINUTES", 30)


def test_auth_disabled_does_not_protect_api(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", False)

    with TestClient(app) as client:
        response = client.get("/api/private-probe")
        status_response = client.get("/api/auth/status")

    assert response.status_code == 404
    assert status_response.json() == {
        "enabled": False,
        "configured": True,
        "authenticated": True,
        "username": None,
    }


def test_auth_enabled_rejects_missing_token(monkeypatch):
    enable_auth(monkeypatch)

    with TestClient(app) as client:
        protected_response = client.get("/api/private-probe")
        health_response = client.get("/api/health")

    assert protected_response.status_code == 401
    assert health_response.status_code == 200


def test_login_issues_token_that_authorizes_api_requests(monkeypatch):
    enable_auth(monkeypatch)

    with TestClient(app) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-password"},
        )
        token = login_response.json()["access_token"]
        protected_response = client.get(
            "/api/private-probe",
            headers={"Authorization": f"Bearer {token}"},
        )
        status_response = client.get(
            "/api/auth/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert login_response.status_code == 200
    assert token
    assert protected_response.status_code == 404
    assert status_response.json()["authenticated"] is True
    assert status_response.json()["username"] == "admin"


def test_query_token_authorizes_eventsource_style_requests(monkeypatch):
    enable_auth(monkeypatch)

    with TestClient(app) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-password"},
        )
        token = login_response.json()["access_token"]
        protected_response = client.get(f"/api/private-probe?access_token={token}")

    assert protected_response.status_code == 404


def test_login_rejects_bad_password(monkeypatch):
    enable_auth(monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "用户名或密码错误"
