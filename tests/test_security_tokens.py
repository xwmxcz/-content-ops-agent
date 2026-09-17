import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.security import (
    HttpsEnforcementMiddleware,
    create_access_token,
    create_resource_ticket,
    decode_access_token,
    decode_resource_ticket,
    is_ticket_path,
)
from src.utils import config


def _configure_auth(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET_KEY", "test-secret-key-with-enough-entropy")
    monkeypatch.setattr(config, "AUTH_TOKEN_EXPIRE_MINUTES", 30)
    monkeypatch.setattr(config, "AUTH_RESOURCE_TICKET_SECONDS", 45)
    monkeypatch.setattr(config, "AUTH_MEDIA_TICKET_SECONDS", 300)


def test_resource_ticket_is_exact_path_scoped_and_not_an_api_bearer(monkeypatch):
    _configure_auth(monkeypatch)
    path = "/api/agent/runs/run_123/stream"
    other_path = "/api/agent/runs/run_456/stream"
    ticket, _ = create_resource_ticket("a" * 32, "b" * 32, path)
    assert decode_resource_ticket(ticket, path) is not None
    assert decode_resource_ticket(ticket, other_path) is None
    assert decode_access_token(ticket) is None


def test_access_bearer_cannot_be_used_as_resource_ticket(monkeypatch):
    _configure_auth(monkeypatch)
    path = "/api/media/42/file"
    token, _ = create_access_token("a" * 32, "b" * 32)
    assert decode_access_token(token) is not None
    assert decode_resource_ticket(token, path) is None


def _signed(payload, header=None):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    message = f"{encode(header or {'alg': 'HS256', 'typ': 'JWT'})}.{encode(payload)}"
    signature = hmac.new(config.AUTH_SECRET_KEY.encode(), message.encode(), hashlib.sha256).digest()
    return message + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def test_new_token_has_explicit_database_subject_session_and_scope(monkeypatch):
    _configure_auth(monkeypatch)
    token, expiry = create_access_token("a" * 32, "b" * 32)
    claims = decode_access_token(token)
    assert claims["sub"] == "a" * 32
    assert claims["sid"] == "b" * 32
    assert claims["v"] == 2
    assert claims["token_use"] == "access"
    assert claims["iss"] == "content-ops-agent"
    assert claims["aud"] == "content-ops-api"
    assert claims["exp"] == expiry


@pytest.mark.parametrize("change", [
    {"sub": "admin"}, {"sid": None}, {"v": 1}, {"token_use": None},
    {"iss": "other"}, {"aud": "other"}, {"exp": True}, {"iat": "yesterday"},
    {"exp": 1}, {"iat": 9999999999},
])
def test_new_token_rejects_invalid_or_legacy_claim_shapes(monkeypatch, change):
    _configure_auth(monkeypatch)
    token, _ = create_access_token("a" * 32, "b" * 32)
    claims = decode_access_token(token)
    claims.update(change)
    assert decode_access_token(_signed(claims)) is None


def test_old_single_admin_tokens_and_missing_type_are_rejected(monkeypatch):
    _configure_auth(monkeypatch)
    legacy = {"sub": "admin", "iat": int(time.time()), "exp": int(time.time()) + 600}
    assert decode_access_token(_signed(legacy)) is None
    token, _ = create_access_token("a" * 32, "b" * 32)
    claims = decode_access_token(token)
    del claims["token_use"]
    assert decode_access_token(_signed(claims)) is None
    del claims["sid"]
    assert decode_access_token(_signed(claims)) is None


@pytest.mark.parametrize("header", [{"alg": "none", "typ": "JWT"}, {"alg": "HS512", "typ": "JWT"}, {"alg": "HS256"}])
def test_signed_tokens_still_require_the_exact_header(monkeypatch, header):
    _configure_auth(monkeypatch)
    token, _ = create_access_token("a" * 32, "b" * 32)
    assert decode_access_token(_signed(decode_access_token(token), header)) is None


def test_token_expires_at_the_boundary_and_rejects_signature_tampering(monkeypatch):
    _configure_auth(monkeypatch)
    now = int(time.time())
    token, _ = create_access_token("a" * 32, "b" * 32, now + 1)
    assert decode_access_token(token) is not None
    monkeypatch.setattr("src.api.security.time.time", lambda: now + 1)
    assert decode_access_token(token) is None
    monkeypatch.setattr("src.api.security.time.time", lambda: now)
    head, payload, signature = token.split(".")
    assert decode_access_token(f"{head}.{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}") is None


@pytest.mark.parametrize("token", [None, "", "a.b", "a.b.c.d", "a.b.非ASCII", "." * 5000])
def test_malformed_tokens_fail_closed_without_exceptions(monkeypatch, token):
    _configure_auth(monkeypatch)
    assert decode_access_token(token) is None


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
