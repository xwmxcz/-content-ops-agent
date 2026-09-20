from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from src.utils import config


class McpClientError(RuntimeError):
    """Raised when the remote MCP server cannot satisfy a request."""


class McpRequestRejectedError(McpClientError):
    """The server refused the request before running the tool."""


class McpOutcomeUnknownError(McpClientError):
    """A non-idempotent tool call was sent and its outcome cannot be determined.

    Publishing to a real platform is not reversible and the provider is not known
    to deduplicate, so neither the REST fallback nor the job retry layer may send
    the request again: the first one may already have been accepted. The error
    classifier treats this as permanent; a person has to check the platform.
    """


# JSON-RPC codes that mean the request never reached the tool: parse error,
# invalid request, method not found, invalid params. Anything else (notably
# -32603 internal error) can be raised after the tool has already acted.
_REJECTED_BEFORE_EXECUTION_CODES = frozenset({-32700, -32600, -32601, -32602})

# httpx failures raised before any request byte is written.
_NEVER_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


class XiaohongshuMcpClient:
    MIN_TIMEOUT_SECONDS = 120.0
    NON_IDEMPOTENT_TOOLS = frozenset({"publish_content", "publish_with_video"})

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = base_url or config.XHS_MCP_URL
        configured_timeout = timeout_seconds or config.XHS_MCP_TIMEOUT_SECONDS
        self.timeout_seconds = max(float(configured_timeout), self.MIN_TIMEOUT_SECONDS)

    async def check_login_status(self) -> dict[str, Any]:
        return await self.call_tool("check_login_status", {})

    async def publish_content(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.call_tool("publish_content", arguments)

    async def publish_with_video(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.call_tool("publish_with_video", arguments)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not config.XHS_MCP_ENABLED:
            raise McpClientError("Xiaohongshu MCP integration is disabled")

        # Until the tools/call request is dispatched, a failure only says the server
        # does not speak MCP, so the REST fallback is safe for every tool. After
        # that point a publish may already have been accepted.
        dispatched = False
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                session_id = await self._initialize(client)
                await self._notify_initialized(client, session_id)
                payload = {
                    "jsonrpc": "2.0",
                    "id": self._request_id(),
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
                dispatched = True
                result = await self._post(client, payload, session_id=session_id)
        except (McpClientError, httpx.HTTPError) as exc:
            if dispatched and name in self.NON_IDEMPOTENT_TOOLS and self._outcome_is_unknown(exc):
                raise self._outcome_unknown(name, exc) from exc
            return await self._call_rest_fallback(name, arguments)
        return self._normalize_tool_result(result)

    async def _initialize(self, client: httpx.AsyncClient) -> str | None:
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "clientInfo": {"name": "content-ops-agent", "version": "0.1.0"},
                "capabilities": {},
            },
        }
        result, headers = await self._post_raw(client, payload)
        if "result" not in result:
            raise McpClientError("MCP initialize response did not include a result")
        return headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")

    async def _notify_initialized(self, client: httpx.AsyncClient, session_id: str | None) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        await self._post(client, payload, session_id=session_id, expect_result=False)

    async def _post(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        expect_result: bool = True,
    ) -> dict[str, Any]:
        body, _ = await self._post_raw(client, payload, session_id=session_id)
        if "error" in body:
            message = body["error"].get("message", "MCP request failed")
            if body["error"].get("code") in _REJECTED_BEFORE_EXECUTION_CODES:
                raise McpRequestRejectedError(message)
            raise McpClientError(message)
        if not expect_result:
            return body
        if "result" not in body:
            raise McpClientError("MCP response did not include a result")
        return body["result"]

    async def _post_raw(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> tuple[dict[str, Any], httpx.Headers]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        response = await client.post(self.base_url, json=payload, headers=headers)
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            data = self._parse_event_stream(response.text)
            if data is None:
                raise McpClientError("MCP server returned a non-JSON response") from exc

        if not isinstance(data, dict):
            raise McpClientError("Unexpected MCP response shape")
        return data, response.headers

    @staticmethod
    def _outcome_is_unknown(exc: Exception) -> bool:
        """Whether a dispatched request may have been acted on despite ``exc``."""
        if isinstance(exc, _NEVER_SENT_ERRORS):
            return False
        if isinstance(exc, httpx.HTTPStatusError):
            # A 4xx is the server declining the request; a 5xx may be a gateway
            # giving up on a backend that is still publishing.
            return exc.response.status_code >= 500
        return not isinstance(exc, McpRequestRejectedError)

    @staticmethod
    def _outcome_unknown(name: str, exc: Exception) -> McpOutcomeUnknownError:
        return McpOutcomeUnknownError(
            f"Xiaohongshu {name} was sent but its outcome is unknown "
            f"({exc.__class__.__name__}: {exc}). The post may already exist: check the platform "
            "before retrying. It was not re-sent automatically to avoid a duplicate post."
        )

    @staticmethod
    def _normalize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
        content_items = result.get("content") or []
        texts: list[str] = []
        parsed: dict[str, Any] | None = None

        for item in content_items:
            if item.get("type") != "text":
                continue
            text = item.get("text", "")
            if text:
                texts.append(text)
                if parsed is None:
                    try:
                        candidate = json.loads(text)
                    except json.JSONDecodeError:
                        candidate = None
                    if isinstance(candidate, dict):
                        parsed = candidate

        text = "\n".join(texts).strip()
        # MCP reports a tool that ran and failed inside a successful JSON-RPC
        # result; without this check a failed publish is recorded as completed.
        if result.get("isError"):
            raise McpClientError(text or "MCP tool reported an error")

        return {
            "raw": result,
            "text": text,
            "data": parsed,
            "content": content_items,
        }

    @staticmethod
    def _request_id() -> str:
        return uuid4().hex

    @staticmethod
    def _parse_event_stream(body: str) -> dict[str, Any] | None:
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            payload = stripped[5:].strip()
            if not payload:
                continue
            try:
                candidate = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                return candidate
        return None

    async def _call_rest_fallback(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        endpoint = self._fallback_endpoint(name)
        method = "GET" if name == "check_login_status" else "POST"
        payload = self._fallback_payload(name, arguments)
        non_idempotent = name in self.NON_IDEMPOTENT_TOOLS
        # Sent as a header so a provider that ignores it cannot reject the body.
        # Whether it deduplicates on the token is the provider's contract.
        request_id = arguments.get("request_id")
        headers = {"Idempotency-Key": str(request_id)} if request_id else None

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                if method == "GET":
                    response = await client.get(endpoint)
                else:
                    response = await client.post(endpoint, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            if non_idempotent and self._outcome_is_unknown(exc):
                raise self._outcome_unknown(name, exc) from exc
            if isinstance(exc, httpx.TimeoutException):
                raise McpClientError(f"Xiaohongshu HTTP API timed out after {int(self.timeout_seconds)}s") from exc
            raise McpClientError(f"Xiaohongshu HTTP API request failed: {exc}") from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            # A structured error body is the API's own verdict; an unreadable one
            # on a 2xx or a gateway 5xx says nothing about what the backend did.
            if non_idempotent and not 400 <= response.status_code < 500:
                raise self._outcome_unknown(name, exc) from exc
            raise McpClientError("Fallback HTTP API returned a non-JSON response") from exc

        if response.status_code >= 400:
            raise McpClientError(self._extract_rest_error(data, response.status_code))
        if not isinstance(data, dict):
            raise McpClientError("Fallback HTTP API returned an unexpected response shape")
        if data.get("success") is False:
            raise McpClientError(self._extract_rest_error(data, response.status_code))

        normalized_data = data.get("data")
        return {
            "raw": data,
            "text": data.get("message", ""),
            "data": normalized_data if isinstance(normalized_data, dict) else {"value": normalized_data},
            "content": [],
        }

    def _fallback_endpoint(self, name: str) -> str:
        root = self._base_origin()
        mapping = {
            "check_login_status": f"{root}/api/v1/login/status",
            "publish_content": f"{root}/api/v1/publish",
            "publish_with_video": f"{root}/api/v1/publish_video",
        }
        if name not in mapping:
            raise McpClientError(f"No fallback HTTP API is available for tool: {name}")
        return mapping[name]

    @staticmethod
    def _fallback_payload(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        visibility_map = {
            "public": "\u516c\u5f00\u53ef\u89c1",
            "self-only": "\u4ec5\u81ea\u5df1\u53ef\u89c1",
            "friends-only": "\u4ec5\u4e92\u5173\u597d\u53cb\u53ef\u89c1",
        }
        visibility = visibility_map.get(
            arguments.get("visibility", "public"),
            arguments.get("visibility", "\u516c\u5f00\u53ef\u89c1"),
        )

        if name == "publish_content":
            return {
                "title": arguments["title"],
                "content": arguments["content"],
                "images": arguments["images"],
                "tags": arguments.get("tags") or [],
                "schedule_at": arguments.get("schedule_at"),
                "is_original": arguments.get("is_original", False),
                "visibility": visibility,
                "products": arguments.get("products") or [],
            }
        if name == "publish_with_video":
            return {
                "title": arguments["title"],
                "content": arguments["content"],
                "video": arguments["video"],
                "tags": arguments.get("tags") or [],
                "schedule_at": arguments.get("schedule_at"),
                "visibility": visibility,
                "products": arguments.get("products") or [],
            }
        return {}

    def _base_origin(self) -> str:
        parsed = urlparse(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _extract_rest_error(data: dict[str, Any], status_code: int) -> str:
        error = data.get("error")
        details = data.get("details")
        message = data.get("message")
        code = data.get("code")

        if error and details:
            return f"{error}: {details}"
        if error:
            return str(error)
        if message and code:
            return f"{message} ({code})"
        if message:
            return str(message)
        return f"Fallback HTTP API request failed with status {status_code}"
