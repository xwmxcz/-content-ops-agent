"""Duplicate-publish guards in the Xiaohongshu MCP client.

Publishing is not reversible and the provider is not known to deduplicate, so
the client must never send a publish twice on its own. These tests drive the
real client over an in-memory transport and count what reached each endpoint.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from src.integrations import mcp_client
from src.integrations.mcp_client import (
    McpClientError,
    McpOutcomeUnknownError,
    XiaohongshuMcpClient,
)
from src.jobs.error_classifier import ErrorClassifier
from src.utils import config

BASE_URL = "http://xhs.test/mcp"
PUBLISH_ARGS = {
    "title": "Title",
    "content": "Body",
    "images": ["/data/a.png"],
    "request_id": "pub-42",
}

ToolCallBehavior = Callable[[httpx.Request], httpx.Response]


class Server:
    """Scriptable stand-in for the MCP endpoint and its REST sibling."""

    def __init__(self) -> None:
        self.initialize: ToolCallBehavior | None = None
        self.tool_call: ToolCallBehavior = lambda request: _rpc_result({"content": [{"type": "text", "text": "ok"}]})
        self.rest: ToolCallBehavior = lambda request: httpx.Response(200, json={"success": True, "data": {"id": "r1"}})
        self.tool_calls: list[dict[str, Any]] = []
        self.rest_requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/mcp":
            self.rest_requests.append(request)
            return self.rest(request)

        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            if self.initialize:
                return self.initialize(request)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        if method == "notifications/initialized":
            return httpx.Response(200, json={"jsonrpc": "2.0"})
        self.tool_calls.append(body["params"])
        return self.tool_call(request)


def _rpc_result(result: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": "1", "result": result})


def _rpc_error(code: int, message: str = "rpc failure") -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": "1", "error": {"code": code, "message": message}})


def _raise(exc_type: type[httpx.HTTPError]) -> ToolCallBehavior:
    def behavior(request: httpx.Request) -> httpx.Response:
        raise exc_type("simulated", request=request)

    return behavior


@pytest.fixture
def server(monkeypatch) -> Server:
    fake = Server()
    real_client = httpx.AsyncClient
    monkeypatch.setattr(config, "XHS_MCP_ENABLED", True)
    monkeypatch.setattr(
        mcp_client.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(fake.handle), **kwargs),
    )
    return fake


@pytest.fixture
def client() -> XiaohongshuMcpClient:
    return XiaohongshuMcpClient(base_url=BASE_URL)


# ─── MCP path ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "behavior",
    [
        _raise(httpx.ReadTimeout),
        _raise(httpx.RemoteProtocolError),
        lambda request: httpx.Response(502, text="bad gateway"),
        lambda request: _rpc_error(-32603, "internal error"),
        lambda request: httpx.Response(200, text="<html>not json</html>"),
    ],
    ids=["read-timeout", "connection-dropped", "gateway-5xx", "rpc-internal-error", "unreadable-2xx"],
)
async def test_dispatched_publish_with_unknown_outcome_is_never_resent(server, client, behavior):
    server.tool_call = behavior

    with pytest.raises(McpOutcomeUnknownError, match="check the platform"):
        await client.publish_content(dict(PUBLISH_ARGS))

    assert len(server.tool_calls) == 1
    assert server.rest_requests == [], "the REST fallback would have published a second time"


@pytest.mark.parametrize(
    "behavior",
    [
        _raise(httpx.ConnectError),
        _raise(httpx.ConnectTimeout),
        lambda request: httpx.Response(404, text="unknown session"),
        lambda request: _rpc_error(-32601, "method not found"),
        lambda request: _rpc_error(-32602, "invalid params"),
    ],
    ids=["connect-error", "connect-timeout", "http-4xx", "rpc-method-not-found", "rpc-invalid-params"],
)
async def test_publish_the_server_provably_did_not_run_falls_back_to_rest(server, client, behavior):
    server.tool_call = behavior

    result = await client.publish_content(dict(PUBLISH_ARGS))

    assert result["data"] == {"id": "r1"}
    assert len(server.rest_requests) == 1


async def test_failure_before_dispatch_falls_back_even_when_it_is_a_timeout(server, client):
    server.initialize = _raise(httpx.ReadTimeout)

    result = await client.publish_content(dict(PUBLISH_ARGS))

    assert server.tool_calls == []
    assert result["data"] == {"id": "r1"}


async def test_read_only_tool_still_falls_back_after_a_dispatched_timeout(server, client):
    server.tool_call = _raise(httpx.ReadTimeout)
    server.rest = lambda request: httpx.Response(200, json={"success": True, "data": {"is_logged_in": True}})

    result = await client.check_login_status()

    assert result["data"] == {"is_logged_in": True}


async def test_tool_level_failure_is_an_error_not_a_completed_publish(server, client):
    server.tool_call = lambda request: _rpc_result(
        {"isError": True, "content": [{"type": "text", "text": "not logged in"}]}
    )

    with pytest.raises(McpClientError, match="not logged in") as excinfo:
        await client.publish_content(dict(PUBLISH_ARGS))

    assert not isinstance(excinfo.value, McpOutcomeUnknownError)
    assert server.rest_requests == [], "the tool already gave its verdict; REST would retry the publish"


# ─── REST fallback ─────────────────────────────────────────────────────────


@pytest.fixture
def rest_only(server) -> Server:
    """MCP handshake fails, so every call goes through the REST fallback."""
    server.initialize = _raise(httpx.ConnectError)
    return server


async def test_rest_fallback_sends_the_stable_request_id_as_a_header(rest_only, client):
    await client.publish_content(dict(PUBLISH_ARGS))

    request = rest_only.rest_requests[0]
    assert request.headers["Idempotency-Key"] == "pub-42"
    assert "request_id" not in json.loads(request.content)


@pytest.mark.parametrize(
    "behavior",
    [
        _raise(httpx.ReadTimeout),
        lambda request: httpx.Response(504, text="gateway timeout"),
        lambda request: httpx.Response(200, text="ok"),
    ],
    ids=["read-timeout", "gateway-5xx-unreadable", "unreadable-2xx"],
)
async def test_rest_publish_with_unknown_outcome_is_reported_as_such(rest_only, client, behavior):
    rest_only.rest = behavior

    with pytest.raises(McpOutcomeUnknownError):
        await client.publish_content(dict(PUBLISH_ARGS))

    assert len(rest_only.rest_requests) == 1


@pytest.mark.parametrize(
    "behavior",
    [
        _raise(httpx.ConnectError),
        lambda request: httpx.Response(500, json={"error": "PUBLISH_FAILED", "details": "title too long"}),
        lambda request: httpx.Response(200, json={"success": False, "message": "not logged in"}),
        lambda request: httpx.Response(400, text="bad request"),
    ],
    ids=["connect-error", "structured-5xx", "success-false", "unreadable-4xx"],
)
async def test_rest_publish_with_a_definite_failure_stays_retriable(rest_only, client, behavior):
    rest_only.rest = behavior

    with pytest.raises(McpClientError) as excinfo:
        await client.publish_content(dict(PUBLISH_ARGS))

    assert not isinstance(excinfo.value, McpOutcomeUnknownError)


# ─── Job retry layer ───────────────────────────────────────────────────────


def test_unknown_outcome_is_never_auto_retried_despite_naming_a_timeout():
    exc = XiaohongshuMcpClient._outcome_unknown("publish_content", httpx.ReadTimeout("timed out"))

    assert "timed out" in str(exc).lower()
    assert ErrorClassifier.classify(exc) == ErrorClassifier.PERMANENT
    assert ErrorClassifier.should_retry(exc, current_attempts=1, max_retries=5) is False


def test_definite_mcp_failures_keep_their_transient_default():
    assert ErrorClassifier.classify(McpClientError("Xiaohongshu HTTP API timed out after 120s")) == "transient"
