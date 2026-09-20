"""How run events get from the pipeline to an SSE stream.

Three things changed here and each is pinned separately:

- streamed tokens are coalesced before they are persisted (one transaction with
  a run-row lock per token meant roughly one per generated token);
- streams are woken by PostgreSQL NOTIFY instead of sweeping the event table
  every 0.4 s, with the table still the source of truth;
- losing the listener degrades to the old sweep rather than to lost events.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from src.api.routes.agent import stream_pipeline_run
from src.api.services import dynamic_pipeline, run_event_hub
from src.api.services.dynamic_pipeline import DynamicPipeline, _TokenBatcher
from src.api.services.run_event_hub import RunEventHub, _libpq_dsn
from src.api.services.sub_agents import SubAgentSpec
from src.models import ContentStyle, ContentType
from src.utils import config

# ─── Token coalescing ──────────────────────────────────────────────────────


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(dynamic_pipeline.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_SECONDS", 0.15)
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_MAX_CHARS", 400)
    return fake


def _batcher() -> tuple[_TokenBatcher, list[str]]:
    emitted: list[str] = []

    async def emit(delta: str) -> None:
        emitted.append(delta)

    return _TokenBatcher(emit), emitted


async def test_first_delta_is_not_held_back(clock):
    batcher, emitted = _batcher()

    await batcher.add("Hel")

    assert emitted == ["Hel"]


async def test_deltas_inside_the_interval_become_one_event(clock):
    batcher, emitted = _batcher()
    await batcher.add("a")

    for delta in ("b", "c", "d"):
        clock.now += 0.04
        await batcher.add(delta)
    assert emitted == ["a"]

    clock.now += 0.04
    await batcher.add("e")
    assert emitted == ["a", "bcde"]


async def test_size_cap_flushes_without_waiting_for_the_interval(clock, monkeypatch):
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_MAX_CHARS", 10)
    batcher, emitted = _batcher()
    await batcher.add("x")

    await batcher.add("123456")
    await batcher.add("7890")

    assert emitted == ["x", "1234567890"]


async def test_flush_emits_the_remainder_once_and_nothing_when_empty(clock):
    batcher, emitted = _batcher()
    await batcher.add("a")
    await batcher.add("tail")

    await batcher.flush()
    await batcher.flush()

    assert emitted == ["a", "tail"]


async def test_zero_interval_restores_one_event_per_delta(clock, monkeypatch):
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_SECONDS", 0)
    batcher, emitted = _batcher()

    for delta in ("a", "b", "c"):
        await batcher.add(delta)

    assert emitted == ["a", "b", "c"]


async def test_no_text_is_lost_or_reordered_by_coalescing(clock):
    batcher, emitted = _batcher()
    text = "流式输出的每一个字都必须按顺序到达客户端。" * 40

    for index, char in enumerate(text):
        clock.now += 0.01 if index % 7 else 0.2
        await batcher.add(char)
    await batcher.flush()

    assert "".join(emitted) == text
    assert len(emitted) < len(text) / 5


# ─── Hub, against a scripted connection ────────────────────────────────────


class _Connection:
    """Yields queued notifications the way psycopg's Connection.notifies does."""

    def __init__(self, script: _Script) -> None:
        self.script = script

    def execute(self, sql: str) -> None:
        self.script.statements.append(sql)

    def notifies(self, timeout: float):
        if self.script.fail_next_listen:
            self.script.fail_next_listen = False
            raise ConnectionError("server closed the connection")
        deadline = time.monotonic() + min(timeout, 0.05)
        while time.monotonic() < deadline:
            with self.script.lock:
                payloads, self.script.pending = self.script.pending, []
            for payload in payloads:
                yield SimpleNamespace(payload=payload)
            time.sleep(0.005)


class _Script:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pending: list[str] = []
        self.statements: list[str] = []
        self.connects = 0
        self.refuse_connections = 0
        self.fail_next_listen = False

    @contextmanager
    def connect(self):
        self.connects += 1
        if self.refuse_connections:
            self.refuse_connections -= 1
            raise ConnectionError("connection refused")
        yield _Connection(self)

    def notify(self, run_id: str) -> None:
        with self.lock:
            self.pending.append(run_id)


@pytest.fixture
def scripted_hub(monkeypatch):
    monkeypatch.setattr(run_event_hub, "_RECONNECT_INITIAL_SECONDS", 0.02)
    monkeypatch.setattr(run_event_hub, "_LISTEN_SLICE_SECONDS", 0.05)
    monkeypatch.setattr(config, "SSE_POLL_INTERVAL_SECONDS", 0.4)
    monkeypatch.setattr(config, "SSE_NOTIFY_FALLBACK_POLL_SECONDS", 30.0)
    script = _Script()
    hub = RunEventHub(connect=script.connect)
    try:
        yield hub, script
    finally:
        hub.stop()


async def _until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition was not reached in time"
        await asyncio.sleep(0.01)


async def test_notification_wakes_only_the_streams_of_that_run(scripted_hub):
    hub, script = scripted_hub
    hub.ensure_started()
    await _until(lambda: hub.healthy)

    with hub.subscribe("run-a") as a, hub.subscribe("run-a") as a2, hub.subscribe("run-b") as b:
        for woken in (a, a2, b):
            woken.clear()
        script.notify("run-a")
        await _until(lambda: a.is_set() and a2.is_set())

        assert not b.is_set()
    assert script.statements == ["LISTEN run_events"]


async def test_wait_returns_on_notification_long_before_the_fallback_poll(scripted_hub):
    hub, script = scripted_hub
    hub.ensure_started()
    await _until(lambda: hub.healthy)

    with hub.subscribe("run-a") as woken:
        woken.clear()
        started = time.monotonic()
        asyncio.get_running_loop().call_later(0.05, script.notify, "run-a")
        await hub.wait(woken)

    assert woken.is_set()
    assert time.monotonic() - started < 5


async def test_streams_sweep_fast_until_the_listener_is_up_and_slow_once_it_is(scripted_hub):
    hub, script = scripted_hub
    script.refuse_connections = 10_000

    hub.ensure_started()
    await _until(lambda: script.connects >= 2)
    assert not hub.healthy
    assert hub.poll_interval() == 0.4

    script.refuse_connections = 0
    await _until(lambda: hub.healthy)
    assert hub.poll_interval() == 30.0


async def test_reconnect_wakes_every_stream_because_notifications_were_missed(scripted_hub):
    hub, script = scripted_hub
    hub.ensure_started()
    await _until(lambda: hub.healthy)

    with hub.subscribe("run-a") as a, hub.subscribe("run-b") as b:
        a.clear()
        b.clear()
        script.fail_next_listen = True
        await _until(lambda: script.connects >= 2 and a.is_set() and b.is_set())

    assert hub.healthy


async def test_unsubscribing_forgets_the_run_and_stop_ends_the_thread(scripted_hub):
    hub, script = scripted_hub
    hub.ensure_started()
    await _until(lambda: hub.healthy)
    with hub.subscribe("run-a"):
        assert "run-a" in hub._subscribers

    assert hub._subscribers == {}
    thread = hub._thread
    hub.stop()
    assert thread is not None and not thread.is_alive()
    assert not hub.healthy


def test_sqlalchemy_url_is_rewritten_for_libpq_without_masking_the_password():
    dsn = _libpq_dsn("postgresql+psycopg://content_ops:s3cret@db.internal:5432/content_ops")

    assert dsn == "postgresql://content_ops:s3cret@db.internal:5432/content_ops"


# ─── Against PostgreSQL ────────────────────────────────────────────────────


@pytest.fixture
def live_hub(store, monkeypatch):
    # A notification that fails to arrive must fail the test, not be papered
    # over by a sweep: push both sweeps far beyond the test's patience.
    monkeypatch.setattr(config, "SSE_POLL_INTERVAL_SECONDS", 60.0)
    monkeypatch.setattr(config, "SSE_NOTIFY_FALLBACK_POLL_SECONDS", 60.0)
    hub = RunEventHub(database_url=store.database_url)
    hub.ensure_started()
    try:
        yield hub
    finally:
        hub.stop()


def _run(store, run_id: str = "run_notify") -> str:
    store.create_run(run_id, "topic", "blog", "casual")
    return run_id


async def test_appending_an_event_wakes_a_subscriber_through_postgres(store, live_hub):
    run_id = _run(store)
    await _until(lambda: live_hub.healthy)

    with live_hub.subscribe(run_id) as woken, live_hub.subscribe("run_other") as other:
        woken.clear()
        other.clear()
        await asyncio.to_thread(store.append_run_event, run_id, "step_start", {"index": 1})
        await _until(woken.is_set)

        assert not other.is_set()


async def test_terminal_transitions_notify_too(store, live_hub):
    run_id = _run(store)
    await _until(lambda: live_hub.healthy)

    with live_hub.subscribe(run_id) as woken:
        woken.clear()
        await asyncio.to_thread(
            lambda: store.transition_run_and_append_event(
                run_id,
                expected_statuses={"running"},
                new_status="cancelled",
                event_type="run_cancelled",
                payload={"run_id": run_id},
            )
        )
        await _until(woken.is_set)


async def test_an_event_discarded_after_the_run_ended_notifies_nobody(store, live_hub):
    run_id = _run(store)
    store.transition_run_and_append_event(
        run_id, expected_statuses={"running"}, new_status="cancelled", event_type="run_cancelled", payload={}
    )
    await _until(lambda: live_hub.healthy)

    with live_hub.subscribe(run_id) as woken:
        await asyncio.sleep(0.3)  # let the cancellation's own notification drain
        woken.clear()
        assert await asyncio.to_thread(store.append_run_event, run_id, "step_token", {"delta": "late"}) is None
        await asyncio.sleep(0.5)

        assert not woken.is_set()


async def test_stream_delivers_a_live_event_without_waiting_for_a_sweep(store, live_hub, monkeypatch):
    run_id = _run(store)
    store.append_run_event(run_id, "plan_ready", {"plan": []})
    monkeypatch.setattr(run_event_hub, "_hub", live_hub)
    await _until(lambda: live_hub.healthy)

    response = await stream_pipeline_run(run_id, store=store, after_seq=None, last_event_id=None)
    frames = response.body_iterator
    assert await anext(frames) == "event: hello\ndata: {}\n\n"
    assert "event: plan_ready" in await anext(frames)

    # The stream is now parked in hub.wait() with a 60 s sweep. Only a
    # notification can deliver this within the timeout below.
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0.2)
    assert not pending.done()
    await asyncio.to_thread(store.append_run_event, run_id, "step_start", {"index": 1})

    frame = await asyncio.wait_for(pending, timeout=5)
    assert frame.startswith("id: 2\nevent: step_start\n")
    await frames.aclose()


# ─── Pipeline ordering with coalescing on ──────────────────────────────────


class _PlannerLLM:
    async def generate_from_prompts(self, **kwargs) -> str:
        return json.dumps(
            [{"index": 1, "agent_id": "writer", "description": "Draft", "instruction": "go", "inputs_from": []}]
        )


class _StreamingRunner:
    """Streams text, calls a tool mid-stream, then streams the rest."""

    def __init__(self, fail_after_streaming: bool = False) -> None:
        self.fail_after_streaming = fail_after_streaming

    async def run(self, spec: SubAgentSpec, token_sink=None, tool_sink=None, **kwargs):
        for char in "before-tool ":
            await token_sink(char)
        await tool_sink("tool_call_result", {"name": "web_search", "status": "completed"})
        for char in "after-tool":
            await token_sink(char)
        if self.fail_after_streaming:
            raise RuntimeError("provider dropped the stream")
        return "before-tool after-tool", 10, 5, 12, 0.0001


def _pipeline_request():
    from src.api.schemas.agent import PipelineRunRequest

    return PipelineRunRequest(
        topic="topic",
        content_type=ContentType.BLOG,
        style=ContentStyle.CASUAL,
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )


def _events(store, run_id: str) -> list[tuple[str, dict]]:
    return [(e["event_type"], json.loads(e["payload"])) for e in store.list_run_events(run_id, limit=1000)]


@pytest.fixture
def coalescing(monkeypatch):
    # An interval no test reaches, so only the ordering flushes can emit.
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_SECONDS", 3600.0)
    monkeypatch.setattr(config, "SSE_TOKEN_BATCH_MAX_CHARS", 10_000)


async def test_text_streamed_before_a_tool_call_is_persisted_before_it(store, coalescing):
    pipeline = DynamicPipeline(store=store, llm=_PlannerLLM(), runner=_StreamingRunner())

    response = await pipeline.run(_pipeline_request())

    events = _events(store, response.run_id)
    step = [(kind, payload.get("delta")) for kind, payload in events if kind in {"step_token", "tool_call_result"}]
    assert step == [
        ("step_token", "b"),
        ("step_token", "efore-tool "),
        ("tool_call_result", None),
        ("step_token", "after-tool"),
    ]
    kinds = [kind for kind, _ in events]
    assert kinds.index("step_complete") > max(i for i, kind in enumerate(kinds) if kind == "step_token")


async def test_text_streamed_before_a_failure_is_persisted_before_step_failed(store, coalescing):
    pipeline = DynamicPipeline(store=store, llm=_PlannerLLM(), runner=_StreamingRunner(fail_after_streaming=True))

    try:
        response = await pipeline.run(_pipeline_request())
        run_id = response.run_id
    except Exception:  # noqa: BLE001 -- a failed single-step run may raise; the events are what is under test
        run_id = store.list_runs(limit=1)[0]["id"]

    # A failed step makes the planner revise and retry, so the step runs more than
    # once. Each attempt must have persisted its whole text before its step_failed.
    attempts: list[str] = []
    streamed = ""
    for kind, payload in _events(store, run_id):
        if kind == "step_token":
            streamed += payload["delta"]
        elif kind == "step_failed":
            attempts.append(streamed)
            streamed = ""

    assert attempts
    assert set(attempts) == {"before-tool after-tool"}
    assert streamed == "", "tokens were persisted after the event that ended their step"
