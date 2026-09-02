from fastapi.testclient import TestClient

from src.api.main import app
from src.utils import config


def enable_auth(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(config, "AUTH_PASSWORD", "secret-password")
    monkeypatch.setattr(config, "AUTH_SECRET_KEY", "test-secret-key-with-enough-entropy")
    monkeypatch.setattr(config, "AUTH_TOKEN_EXPIRE_MINUTES", 30)


def test_auth_disabled_does_not_protect_api(store, monkeypatch):
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


def test_auth_enabled_rejects_missing_token(store, monkeypatch):
    enable_auth(monkeypatch)

    with TestClient(app) as client:
        protected_response = client.get("/api/private-probe")
        health_response = client.get("/api/health")

    assert protected_response.status_code == 401
    assert health_response.status_code == 200


def test_login_issues_token_that_authorizes_api_requests(store, monkeypatch):
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


def test_resource_cookie_never_authorizes_general_api(store, monkeypatch):
    enable_auth(monkeypatch)
    with TestClient(app) as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-password"},
        )
        response = client.get("/api/private-probe")
    assert response.status_code == 401


def test_general_query_bearer_is_rejected(store, monkeypatch):
    enable_auth(monkeypatch)

    with TestClient(app) as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-password"},
        )
        token = login_response.json()["access_token"]
        protected_response = client.get(f"/api/private-probe?access_token={token}")

    assert protected_response.status_code == 401


def test_http_only_cookie_authorizes_only_its_pipeline_stream_without_url_secret(store, monkeypatch):
    enable_auth(monkeypatch)
    monkeypatch.setattr(config, "APP_ENV", "production")
    run_id = "run_ticket_test"
    path = f"/api/agent/runs/{run_id}/stream"
    store.create_run(run_id=run_id, topic="t", content_type="blog", style="professional")
    store.transition_run_and_append_event(
        run_id,
        expected_statuses={"running"},
        new_status="completed",
        event_type="run_complete",
        payload={"ok": True},
    )

    with TestClient(app, base_url="https://testserver") as client:
        login_response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-password"},
        )
        token = login_response.json()["access_token"]
        assert "HttpOnly" in login_response.headers["set-cookie"]
        assert "Secure" in login_response.headers["set-cookie"]
        stream_response = client.get(path)
        client.cookies.clear()
        bearer_in_url = client.get(f"{path}?access_ticket={token}")

    assert stream_response.status_code == 200
    assert "event: run_complete" in stream_response.text
    assert bearer_in_url.status_code == 401


def test_http_only_cookie_supports_browser_media_path(store, monkeypatch):
    enable_auth(monkeypatch)
    monkeypatch.setattr(config, "APP_ENV", "production")
    path = "/api/media/999999/file"
    with TestClient(app, base_url="https://testserver") as client:
        client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-password"},
        )
        media_response = client.get(path)
    assert media_response.status_code == 404  # authorized; asset simply does not exist


def test_resource_ticket_endpoint_is_gone_in_production(store, monkeypatch):
    enable_auth(monkeypatch)
    monkeypatch.setattr(config, "APP_ENV", "production")
    with TestClient(app, base_url="https://testserver") as client:
        token = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret-password"},
        ).json()["access_token"]
        response = client.post(
            "/api/auth/resource-ticket",
            headers={"Authorization": f"Bearer {token}"},
            json={"path": "/api/media/1/file"},
        )
    assert response.status_code == 410


def test_login_rejects_bad_password(store, monkeypatch):
    enable_auth(monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "用户名或密码错误"
