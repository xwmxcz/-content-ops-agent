"""POST /api/agent/chat/stream: the same turn as POST /chat, reported while it runs.

The contract worth pinning:

- streaming is an observer: what is returned and persisted matches POST /chat;
- text streamed ahead of a tool call is withdrawn, because only the last round
  is the reply;
- the progress feed can fail, or the client can leave, without failing the turn,
  which may be half-way through a write tool.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from src.api.dependencies import get_chat_agent_service, get_store
from src.api.main import app
from src.api.routes import agent as agent_routes
from src.api.schemas.agent import ChatIntent, ChatRequest
from src.api.services.chat_agent import ChatAgentExecutionError, ChatAgentService
from src.models import ContentType, GeneratedContent
from src.utils import config

Round = list[AIMessageChunk | Exception] | Exception


class _Intent:
    def __init__(self, intent: ChatIntent) -> None:
        self.intent = intent

    async def recognize(self, **kwargs: Any) -> ChatIntent:
        return self.intent


class _OneShotModel:
    """A model with no ``astream``: the shape the existing test doubles have."""

    def __init__(self, rounds: list[Round]) -> None:
        self.rounds = list(rounds)
        self.astream_calls = 0
        self.ainvoke_calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.ainvoke_calls += 1
        script = self.rounds.pop(0)
        assert not isinstance(script, Exception)
        merged = script[0]
        for chunk in script[1:]:
            merged = merged + chunk
        return AIMessage(content=merged.content, tool_calls=merged.tool_calls)


class _StreamingModel(_OneShotModel):
    """Plays scripted rounds; each round is the chunks one model call streams."""

    async def astream(self, messages):
        self.astream_calls += 1
        script = self.rounds.pop(0)
        if isinstance(script, Exception):
            raise script
        for chunk in script:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


def _text(*pieces: str) -> list[AIMessageChunk]:
    return [AIMessageChunk(content=piece) for piece in pieces]


def _tool_call(name: str, args: dict[str, Any], preamble: str = "") -> list[AIMessageChunk]:
    chunks = [AIMessageChunk(content=preamble)] if preamble else []
    chunks.append(
        AIMessageChunk(
            content="",
            tool_call_chunks=[{"name": name, "args": json.dumps(args), "id": "call_1", "index": 0}],
        )
    )
    return chunks


@pytest.fixture(autouse=True)
def no_planner(monkeypatch):
    # The planner is a separate, non-streamed model call; keep it out of the script.
    monkeypatch.setattr(config, "CHAT_PLAN_ENABLED", False)


def _service(store, model: _OneShotModel, intent: ChatIntent | None = None) -> ChatAgentService:
    return ChatAgentService(
        store=store,
        model_factory=lambda provider, name, temperature, max_tokens: model,
        intent_recognizer=_Intent(intent or ChatIntent(name="unknown", confidence=0.9)),
    )


def _request(message: str = "hello", thread_id: str = "thread-stream") -> ChatRequest:
    return ChatRequest(message=message, thread_id=thread_id, provider="siliconflow", model="Qwen/Qwen2.5-7B-Instruct")


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.events]

    def text(self) -> str:
        return "".join(payload["delta"] for kind, payload in self.events if kind == "token")


# ─── Service ───────────────────────────────────────────────────────────────


async def test_streamed_tokens_add_up_to_the_reply_that_is_returned_and_persisted(store):
    service = _service(store, _StreamingModel([_text("你好，", "这是", "流式回复。")]))
    seen = _Recorder()

    response = await service.chat(_request(), sink=seen)

    assert seen.kinds() == ["turn_start", "intent", "token", "token", "token"]
    assert seen.text() == response.response == "你好，这是流式回复。"
    assert seen.events[0][1]["thread_id"] == "thread-stream"
    persisted = store.list_agent_messages("thread-stream", limit=10)
    assert [(m["role"], m["content"]) for m in persisted] == [("user", "hello"), ("assistant", "你好，这是流式回复。")]


async def test_streaming_does_not_change_what_a_turn_returns(store):
    script = [_text("Same ", "answer.")]
    plain = await _service(store, _StreamingModel(list(script))).chat(_request(thread_id="thread-plain"))
    streamed = await _service(store, _StreamingModel(list(script))).chat(
        _request(thread_id="thread-streamed"), sink=_Recorder()
    )

    assert streamed.response == plain.response
    assert streamed.tool_events == plain.tool_events
    assert streamed.intent == plain.intent


async def test_text_streamed_ahead_of_a_tool_call_is_withdrawn(store):
    store.save_content(GeneratedContent(title="Existing", content="body", content_type=ContentType.BLOG))
    model = _StreamingModel(
        [
            _tool_call("list_recent_contents", {"limit": 5}, preamble="Let me look that up. "),
            _text("You have ", "one draft."),
        ]
    )
    intent = ChatIntent(name="content_search", confidence=0.9, allowed_tools=["list_recent_contents"])
    seen = _Recorder()

    response = await _service(store, model, intent).chat(_request("what did I write?"), sink=seen)

    assert seen.kinds() == [
        "turn_start",
        "intent",
        "token",
        "draft_reset",
        "tool_start",
        "tool_end",
        "token",
        "token",
    ]
    assert response.response == "You have one draft."
    tool_end = dict(seen.events)["tool_end"]["event"]
    assert tool_end["name"] == "list_recent_contents"
    assert tool_end["status"] == "completed"
    assert [event.name for event in response.tool_events] == ["list_recent_contents"]


async def test_a_failing_progress_feed_does_not_fail_the_turn(store):
    async def broken_sink(event_type: str, payload: dict[str, Any]) -> None:
        raise ConnectionResetError("client went away")

    response = await _service(store, _StreamingModel([_text("still ", "answered")])).chat(_request(), sink=broken_sink)

    assert response.response == "still answered"
    assert store.list_agent_messages("thread-stream", limit=10)[-1]["content"] == "still answered"


async def test_model_without_streaming_support_still_answers(store):
    model = _OneShotModel([_text("one-shot reply")])
    seen = _Recorder()

    response = await _service(store, model).chat(_request(), sink=seen)

    assert response.response == "one-shot reply"
    assert "token" not in seen.kinds()


async def test_provider_that_rejects_streaming_falls_back_before_any_text_was_shown(store):
    model = _StreamingModel([RuntimeError("stream is not supported"), _text("fallback reply")])

    response = await _service(store, model).chat(_request(), sink=_Recorder())

    assert response.response == "fallback reply"
    assert (model.astream_calls, model.ainvoke_calls) == (1, 1)


async def test_stream_that_dies_mid_reply_is_not_silently_answered_twice(store):
    model = _StreamingModel([[AIMessageChunk(content="Half of an ans"), RuntimeError("connection reset")]])
    seen = _Recorder()

    with pytest.raises(ChatAgentExecutionError):
        await _service(store, model).chat(_request(), sink=seen)

    assert model.ainvoke_calls == 0, "a second attempt would show the user two different answers"
    assert seen.text() == "Half of an ans"
    assert store.list_agent_messages("thread-stream", limit=10)[-1]["status"] == "failed"


async def test_anthropic_block_content_streams_as_text_not_json(store):
    blocks = [
        AIMessageChunk(content=[{"type": "text", "text": "块状", "index": 0}]),
        AIMessageChunk(content=[{"type": "text", "text": "内容", "index": 0}]),
    ]
    seen = _Recorder()

    response = await _service(store, _StreamingModel([blocks])).chat(_request(), sink=seen)

    assert seen.text() == "块状内容"
    assert response.response == "块状内容"


# ─── Route ─────────────────────────────────────────────────────────────────


def _frames(body: str) -> list[tuple[str, dict[str, Any]]]:
    frames = []
    for block in body.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if not lines:
            continue
        fields = dict(line.split(": ", 1) for line in lines)
        frames.append((fields["event"], json.loads(fields["data"])))
    return frames


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _payload(thread_id: str = "thread-http") -> dict[str, Any]:
    return {"message": "hello", "thread_id": thread_id, "provider": "siliconflow", "model": "Qwen/Qwen2.5-7B-Instruct"}


def test_stream_ends_with_the_response_the_plain_endpoint_would_return(client, store):
    app.dependency_overrides[get_chat_agent_service] = lambda: _service(store, _StreamingModel([_text("Hi ", "there")]))

    response = client.post("/api/agent/chat/stream", json=_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _frames(response.text)
    assert [kind for kind, _ in frames] == ["turn_start", "intent", "token", "token", "done"]
    done = frames[-1][1]
    assert done["response"] == "Hi there"
    assert done["thread_id"] == "thread-http"
    messages = client.get("/api/agent/threads/thread-http/messages").json()
    assert messages[-1]["id"] == done["message_id"]
    assert messages[-1]["content"] == "Hi there"


def test_failure_after_the_headers_were_sent_arrives_as_an_error_event(client, store):
    def no_api_key(provider, name, temperature, max_tokens):
        raise ValueError("Missing API key for provider: siliconflow")

    app.dependency_overrides[get_chat_agent_service] = lambda: ChatAgentService(
        store=store, model_factory=no_api_key, intent_recognizer=_Intent(ChatIntent(name="unknown", confidence=0.9))
    )

    response = client.post("/api/agent/chat/stream", json=_payload())

    assert response.status_code == 200
    kind, payload = _frames(response.text)[-1]
    assert kind == "error"
    assert payload["status"] == 502
    assert "Missing API key" in payload["detail"]


def test_unexpected_failure_does_not_leak_internals_to_the_client(client, store, monkeypatch):
    service = _service(store, _StreamingModel([_text("unused")]))

    async def explode(request, sink=None):
        raise RuntimeError("postgresql://content_ops:s3cret@db/internal")

    monkeypatch.setattr(service, "chat", explode)
    app.dependency_overrides[get_chat_agent_service] = lambda: service

    kind, payload = _frames(client.post("/api/agent/chat/stream", json=_payload()).text)[-1]

    assert kind == "error"
    assert payload == {"status": 500, "detail": "The chat turn failed unexpectedly"}


async def test_turn_finishes_and_is_persisted_after_the_client_disconnects(store):
    release = asyncio.Event()

    class _SlowModel(_StreamingModel):
        async def astream(self, messages):
            yield AIMessageChunk(content="first ")
            await release.wait()
            yield AIMessageChunk(content="rest")

    service = _service(store, _SlowModel([]))
    response = await agent_routes.chat_stream(_request(thread_id="thread-gone"), agent_service=service, _budget=None)
    frames = response.body_iterator
    seen = [await anext(frames) for _ in range(3)]
    assert "first " in seen[-1]

    await frames.aclose()  # the browser tab is closed mid-reply
    release.set()
    deadline = time.monotonic() + 5
    while agent_routes._CHAT_TURNS:
        assert time.monotonic() < deadline, "the turn did not finish"
        await asyncio.sleep(0.01)

    assert store.list_agent_messages("thread-gone", limit=10)[-1]["content"] == "first rest"
