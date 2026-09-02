from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.security import (
    create_access_token,
    create_resource_ticket,
    decode_access_token,
    decode_resource_ticket,
    is_ticket_path,
    HttpsEnforcementMiddleware,
)
from src.utils import config


def _configure_auth(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    monkeypatch.setattr(config, "AUTH_USERNAME", "admin")
    monkeypatch.setattr(config, "AUTH_PASSWORD", "secret-password")
    monkeypatch.setattr(config, "AUTH_SECRET_KEY", "test-secret-key-with-enough-entropy")
    monkeypatch.setattr(config, "AUTH_TOKEN_EXPIRE_MINUTES", 30)
    monkeypatch.setattr(config, "AUTH_RESOURCE_TICKET_SECONDS", 45)
    monkeypatch.setattr(config, "AUTH_MEDIA_TICKET_SECONDS", 300)


def test_resource_ticket_is_exact_path_scoped_and_not_an_api_bearer(monkeypatch):
    _configure_auth(monkeypatch)
    path = "/api/agent/runs/run_123/stream"
    other_path = "/api/agent/runs/run_456/stream"
    ticket, _ = create_resource_ticket("admin", path)
    assert decode_resource_ticket(ticket, path) is not None
    assert decode_resource_ticket(ticket, other_path) is None
    assert decode_access_token(ticket) is None


def test_access_bearer_cannot_be_used_as_resource_ticket(monkeypatch):
    _configure_auth(monkeypatch)
    path = "/api/media/42/file"
    token, _ = create_access_token("admin")
    assert decode_access_token(token) is not None
    assert decode_resource_ticket(token, path) is None


def test_resource_ticket_scope_allowlist_is_narrow():
    assert is_ticket_path("/api/agent/runs/run_abc-123/stream")
    assert is_ticket_path("/api/media/42/file")
    assert not is_ticket_path("/api/private-probe")
    assert not is_ticket_path("/api/media/42")
    assert not is_ticket_path("/api/agent/threads/default/messages")


def test_https_enforcement_rejects_spoofed_forwarded_proto_from_untrusted_client(monkeypatch):
    monkeypatch.setattr(config, "ENFORCE_HTTPS", True)
    monkeypatch.setattr(config, "TRUSTED_PROXY_CIDRS", [])
    test_app = FastAPI()
    test_app.add_middleware(HttpsEnforcementMiddleware)

    @test_app.get("/api/private")
    def private():
        return {"ok": True}

    client = TestClient(test_app, base_url="http://plain-http")
    assert client.get("/api/private").status_code == 426
    assert client.get(
        "/api/private", headers={"X-Forwarded-Proto": "https"}
    ).status_code == 426

    monkeypatch.setattr(config, "TRUSTED_PROXY_CIDRS", ["127.0.0.1/32"])
    trusted_proxy = TestClient(
        test_app,
        base_url="http://plain-http",
        client=("127.0.0.1", 50000),
    )
    assert trusted_proxy.get(
        "/api/private", headers={"X-Forwarded-Proto": "https"}
    ).status_code == 200
    assert TestClient(test_app, base_url="https://direct-tls").get("/api/private").status_code == 200


def test_frontend_proxy_logs_strip_query_strings_and_compose_is_loopback_only():
    root = Path(__file__).resolve().parents[1]
    nginx = (root / "frontend/nginx.conf").read_text(encoding="utf-8")
    log_format = nginx.split("log_format sanitized", 1)[1].split("access_log", 1)[0]
    assert "$uri" in log_format
    assert "$request_uri" not in log_format
    assert '"$request "' not in log_format
    assert "$http_referer" not in log_format
    assert "access_log /var/log/nginx/access.log sanitized;" in nginx
    assert "geo $trusted_forwarding_proxy" in nginx
    assert '~*^1:https$ https;' in nginx
    assert "map $args $has_url_credential" in nginx
    assert "~*(^|&)(access_token|access_ticket)= 1;" in nginx
    assert "if ($has_url_credential) { return 400; }" in nginx
    proxy_pass = next(
        line.strip() for line in nginx.splitlines() if line.strip().startswith("proxy_pass ")
    )
    assert "$request_uri" not in proxy_pass
    assert proxy_pass == "proxy_pass $api_upstream$uri$is_args$args;"

    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert '127.0.0.1:${FRONTEND_PORT:-8088}:80' in compose
    assert "ENFORCE_HTTPS: ${ENFORCE_HTTPS:-true}" in compose
    assert "TRUSTED_PROXY_CIDRS: ${TRUSTED_PROXY_CIDRS:-172.16.0.0/12}" in compose
    assert "proxy_headers=False" in (root / "server.py").read_text(encoding="utf-8")
    assert 'forwarded_allow_ips = ""' in (root / "gunicorn.conf.py").read_text(encoding="utf-8")
