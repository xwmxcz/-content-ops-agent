"""The lease reaper as a deployed service: liveness heartbeat and healthcheck.

The sweep logic itself is covered against PostgreSQL in test_job_lease.py. These
tests cover what makes the daemon deployable, and need no database.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from src.jobs import reaper
from src.utils import config


class _Store:
    """Counts sweeps; optionally fails every one of them."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sweeps = 0

    def find_expired_lease_jobs(self, limit: int):
        self.sweeps += 1
        if self.fail:
            raise ConnectionError("database unreachable")
        return []


async def _run_one_iteration(store: _Store, heartbeat_path) -> None:
    stop = asyncio.Event()
    task = asyncio.ensure_future(
        reaper.run_reaper_loop(store, interval_seconds=30, stop_event=stop, heartbeat_path=heartbeat_path)
    )
    for _ in range(200):
        if store.sweeps:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=5)


def _age(path, seconds: float) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


async def test_loop_touches_the_heartbeat_after_each_sweep(tmp_path):
    heartbeat = tmp_path / "state" / "reaper.heartbeat"

    await _run_one_iteration(_Store(), heartbeat)

    assert reaper.heartbeat_is_fresh(heartbeat, interval_seconds=30)


async def test_failing_sweep_still_reports_a_live_loop(tmp_path):
    # Restarting the reaper cannot fix an unreachable database, so an outage
    # must not also push the container into a restart loop.
    heartbeat = tmp_path / "reaper.heartbeat"
    store = _Store(fail=True)

    await _run_one_iteration(store, heartbeat)

    assert store.sweeps >= 1
    assert reaper.heartbeat_is_fresh(heartbeat, interval_seconds=30)


def test_missing_heartbeat_is_not_fresh(tmp_path):
    assert reaper.heartbeat_is_fresh(tmp_path / "never-written", interval_seconds=60) is False


def test_heartbeat_tolerates_one_slow_sweep_but_not_a_wedged_loop(tmp_path):
    heartbeat = tmp_path / "reaper.heartbeat"
    heartbeat.touch()

    _age(heartbeat, 150)
    assert reaper.heartbeat_is_fresh(heartbeat, interval_seconds=60) is True
    _age(heartbeat, 200)
    assert reaper.heartbeat_is_fresh(heartbeat, interval_seconds=60) is False


@pytest.mark.parametrize(("age_seconds", "exit_code"), [(0, 0), (10_000, 1)])
def test_healthcheck_exit_code_follows_heartbeat_age(tmp_path, monkeypatch, age_seconds, exit_code):
    heartbeat = tmp_path / "reaper.heartbeat"
    heartbeat.touch()
    _age(heartbeat, age_seconds)
    monkeypatch.setattr(config, "JOB_REAPER_HEARTBEAT_FILE", str(heartbeat))

    with pytest.raises(SystemExit) as excinfo:
        reaper.main(["--healthcheck"])

    assert excinfo.value.code == exit_code


def test_loop_mode_refuses_to_run_as_a_dry_run(capsys):
    with pytest.raises(SystemExit) as excinfo:
        reaper.main(["--loop"])

    assert excinfo.value.code == 2
    assert "--loop requires --execute" in capsys.readouterr().err
