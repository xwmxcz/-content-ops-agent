"""Wakes SSE run streams when their run gets a new event.

Streams used to sweep ``agent_run_events`` every ``SSE_POLL_INTERVAL_SECONDS``,
so an idle stream cost 2.5 queries a second for as long as it was open. Writers
now ``pg_notify`` the run id inside the transaction that inserts the event, and
this hub turns that notification into an ``asyncio.Event`` for the streams
subscribed to the run.

The event table stays the source of truth. A notification carries no data and
is allowed to be lost: a stream always re-reads the table when woken, and keeps
sweeping at ``SSE_NOTIFY_FALLBACK_POLL_SECONDS`` while the listener is healthy,
or at the original fast interval while it is not. Losing the listener therefore
degrades latency and load back to the old behaviour, never correctness.

One listener per process: a thread holding one autocommit connection. A thread
rather than psycopg's async connection because the latter cannot run on the
Proactor event loop that asyncio uses by default on Windows.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import psycopg
from sqlalchemy.engine import make_url

from src.storage.repositories.run_repository import RUN_EVENTS_CHANNEL
from src.utils import config
from src.utils.structured_logging import log_event

logger = logging.getLogger(__name__)

_RECONNECT_INITIAL_SECONDS = 1.0
_RECONNECT_MAX_SECONDS = 30.0
# How long one blocking wait for notifications lasts before the thread rechecks
# whether it was asked to stop; this bounds shutdown time, not delivery latency.
_LISTEN_SLICE_SECONDS = 1.0

Connector = Callable[[], AbstractContextManager[Any]]


def _libpq_dsn(database_url: str) -> str:
    """The SQLAlchemy URL without its driver suffix, which libpq rejects."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


class RunEventHub:
    def __init__(self, database_url: str | None = None, connect: Connector | None = None) -> None:
        self._database_url = database_url
        self._connect = connect or self._default_connect
        # Guards the subscriber table, which the listener thread reads while the
        # event loop adds and removes streams.
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._healthy = threading.Event()

    # ─── Stream side ──────────────────────────────────────────────────────

    @property
    def healthy(self) -> bool:
        """Whether notifications are currently being received."""
        return self._healthy.is_set()

    def poll_interval(self) -> float:
        """How long a stream may sleep before it must look at the table itself."""
        if self.healthy:
            return max(config.SSE_NOTIFY_FALLBACK_POLL_SECONDS, config.SSE_POLL_INTERVAL_SECONDS)
        return config.SSE_POLL_INTERVAL_SECONDS

    @contextmanager
    def subscribe(self, run_id: str) -> Iterator[asyncio.Event]:
        """An event that is set whenever ``run_id`` may have new rows.

        Subscribe before the first read and clear the event before every read: a
        notification that lands during a read then still wakes the next wait,
        instead of being lost between "read found nothing" and "start waiting".
        """
        entry = (asyncio.get_running_loop(), asyncio.Event())
        with self._lock:
            self._subscribers.setdefault(run_id, set()).add(entry)
        try:
            yield entry[1]
        finally:
            with self._lock:
                entries = self._subscribers.get(run_id)
                if entries is not None:
                    entries.discard(entry)
                    if not entries:
                        del self._subscribers[run_id]

    async def wait(self, woken: asyncio.Event) -> None:
        """Sleep until ``woken`` is set or the current poll interval elapses."""
        timeout = self.poll_interval()
        if timeout <= 0:
            await asyncio.sleep(0)
            return
        try:
            await asyncio.wait_for(woken.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    def publish(self, run_id: str) -> None:
        """Wake the streams of one run. Called from the listener thread."""
        with self._lock:
            entries = list(self._subscribers.get(run_id, ()))
        for loop, woken in entries:
            try:
                loop.call_soon_threadsafe(woken.set)
            except RuntimeError:
                # The stream's loop closed between the lookup and the call.
                continue

    def _wake_all(self) -> None:
        # After a reconnect, notifications sent while disconnected are gone.
        with self._lock:
            run_ids = list(self._subscribers)
        for run_id in run_ids:
            self.publish(run_id)

    # ─── Listener side ────────────────────────────────────────────────────

    def ensure_started(self) -> None:
        """Start the listener on first use, so processes that never stream pay nothing."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._listen_forever, name="run-event-listener", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        self._healthy.clear()

    def _default_connect(self) -> AbstractContextManager[Any]:
        return psycopg.connect(
            _libpq_dsn(self._database_url or config.DATABASE_URL),
            autocommit=True,
            connect_timeout=5,
        )

    def _listen_forever(self) -> None:
        delay = _RECONNECT_INITIAL_SECONDS
        while not self._stop.is_set():
            try:
                with self._connect() as connection:
                    connection.execute(f"LISTEN {RUN_EVENTS_CHANNEL}")
                    self._healthy.set()
                    delay = _RECONNECT_INITIAL_SECONDS
                    log_event(logger, "run_event_listener_connected")
                    self._wake_all()
                    while not self._stop.is_set():
                        for notification in connection.notifies(timeout=_LISTEN_SLICE_SECONDS):
                            self.publish(notification.payload)
            except Exception as exc:  # noqa: BLE001 -- the listener must outlive any database failure
                if self._stop.is_set():
                    break
                log_event(
                    logger,
                    "run_event_listener_disconnected",
                    level=logging.WARNING,
                    error_class=exc.__class__.__name__,
                    retry_in_seconds=delay,
                )
            finally:
                self._healthy.clear()
            if self._stop.wait(delay):
                break
            delay = min(delay * 2, _RECONNECT_MAX_SECONDS)


class _DisabledHub(RunEventHub):
    """Keeps the stream code on one path when notifications are switched off."""

    def ensure_started(self) -> None:
        return


_hub: RunEventHub | None = None
_hub_lock = threading.Lock()


def get_run_event_hub() -> RunEventHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = RunEventHub() if config.SSE_NOTIFY_ENABLED else _DisabledHub()
        return _hub


def shutdown_run_event_hub() -> None:
    global _hub
    with _hub_lock:
        hub, _hub = _hub, None
    if hub is not None:
        hub.stop()
