"""SSE run-stream contract tests (P1-06).

These exercise the stream generator directly with an in-memory store double, so
they run without PostgreSQL. The contract they pin down is what the frontend's
resume logic depends on:

- every run event carries an `id:` equal to its store sequence
- `after_seq` / `Last-Event-ID` resume strictly after the given sequence
- terminal events end the stream
- silence produces browser-visible ping frames, without sequence numbers
"""

import asyncio
import json

import pytest
from fastapi import HTTPException

from src.api.routes.agent import _parse_last_event_id, stream_pipeline_run
from src.utils import config


_DEFAULT_RUN = object()


class FakeStore:
    """Minimal ContentStore stand-in for the two methods the stream uses."""

    def __init__(self, events=None, run=_DEFAULT_RUN):
        self._events = list(events or [])
        # A sentinel is required so `run=None` can mean "this run does not exist"
        # rather than "use the default run".
        self._run = {"id": "run-1", "status": "running"} if run is _DEFAULT_RUN else run
        self.calls = []

    def get_run(self, run_id):
        return self._run

    def list_run_events(self, run_id, after_seq=0, limit=100):
        self.calls.append(after_seq)
        matching = [e for e in self._events if e["seq"] > after_seq]
        return matching[:limit]


def event(seq, event_type, payload=None):
    return {
        "seq": seq,
        "event_type": event_type,
        "payload": json.dumps(payload or {}),
    }


async def collect(store, *, after_seq=None, last_event_id=None, limit=50):
    """Drains the stream, stopping at the terminal event or a frame budget."""
    response = await stream_pipeline_run(
        "run-1", store=store, after_seq=after_seq, last_event_id=last_event_id
    )
    frames = []
    async for chunk in response.body_iterator:
        frames.append(chunk)
        if len(frames) >= limit:
            break
    return frames


@pytest.fixture(autouse=True)
def fast_stream(monkeypatch):
    """Collapses the poll interval so tests do not wait on wall-clock time."""
    monkeypatch.setattr(config, "SSE_POLL_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(config, "SSE_KEEPALIVE_SECONDS", 0)
    monkeypatch.setattr(config, "SSE_STREAM_TIMEOUT_SECONDS", 5)


def test_missing_run_is_404():
    store = FakeStore(run=None)
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(stream_pipeline_run("run-1", store=store, after_seq=None, last_event_id=None))
    assert excinfo.value.status_code == 404


def test_stream_opens_with_hello_then_replays_events():
    store = FakeStore([event(1, "plan_ready", {"plan": []}), event(2, "run_complete", {})])

    frames = asyncio.run(collect(store))

    assert frames[0] == "event: hello\ndata: {}\n\n"
    assert "event: plan_ready" in frames[1]
    assert "event: run_complete" in frames[-1]


def test_every_event_carries_its_sequence_as_the_sse_id():
    """The frontend's resume cursor is this id; without it, replay is unbounded."""
    store = FakeStore([event(4, "step_start", {"index": 1}), event(9, "run_failed", {})])

    frames = asyncio.run(collect(store))

    assert frames[1].startswith("id: 4\n")
    assert frames[2].startswith("id: 9\n")


def test_terminal_event_ends_the_stream():
    store = FakeStore(
        [event(1, "run_complete", {}), event(2, "step_token", {"index": 1, "delta": "late"})]
    )

    frames = asyncio.run(collect(store))

    assert len(frames) == 2
    assert "step_token" not in "".join(frames)


@pytest.mark.parametrize("terminal", ["run_complete", "run_failed", "run_cancelled"])
def test_all_terminal_event_types_end_the_stream(terminal):
    store = FakeStore([event(1, terminal, {})])

    frames = asyncio.run(collect(store))

    assert len(frames) == 2
    assert f"event: {terminal}" in frames[1]


def test_after_seq_resumes_strictly_after_the_cursor():
    store = FakeStore(
        [
            event(1, "step_token", {"delta": "a"}),
            event(2, "step_token", {"delta": "b"}),
            event(3, "run_complete", {}),
        ]
    )

    frames = asyncio.run(collect(store, after_seq=2))

    body = "".join(frames)
    assert '"a"' not in body
    assert '"b"' not in body
    assert "event: run_complete" in body


def test_last_event_id_header_is_used_when_after_seq_is_absent():
    store = FakeStore([event(1, "step_token", {"delta": "a"}), event(2, "run_complete", {})])

    frames = asyncio.run(collect(store, last_event_id="1"))

    assert '"a"' not in "".join(frames)
    assert store.calls[0] == 1


def test_after_seq_wins_over_last_event_id():
    store = FakeStore([event(5, "run_complete", {})])

    asyncio.run(collect(store, after_seq=4, last_event_id="1"))

    assert store.calls[0] == 4


def test_after_seq_zero_is_honoured_rather_than_treated_as_absent():
    """0 means "from the beginning" and must not fall through to the header."""
    store = FakeStore([event(1, "run_complete", {})])

    asyncio.run(collect(store, after_seq=0, last_event_id="99"))

    assert store.calls[0] == 0


def test_keepalive_is_emitted_while_no_events_arrive():
    store = FakeStore([])

    frames = asyncio.run(collect(store, limit=4))

    assert frames[0] == "event: hello\ndata: {}\n\n"
    assert frames[1:] == [": keepalive\nevent: ping\ndata: {}\n\n"] * (len(frames) - 1)


def test_keepalive_carries_no_sequence_number():
    """A keepalive must never look like a replayable event to the client."""
    store = FakeStore([event(7, "step_token", {"index": 1, "delta": "a"})])

    frames = asyncio.run(collect(store, limit=4))

    assert frames[1].startswith("id: 7\n")
    for frame in frames[2:]:
        assert "id:" not in frame
        assert "event: ping\n" in frame
        assert "data: {}\n\n" in frame
    assert store.calls[-1] == 7


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 0),
        ("", 0),
        ("7", 7),
        ("0", 0),
        ("-3", 0),
        ("not-a-number", 0),
        ("12abc", 0),
    ],
)
def test_last_event_id_parsing_is_fail_safe(value, expected):
    """A malformed cursor must replay from the start, never crash the stream."""
    assert _parse_last_event_id(value) == expected
