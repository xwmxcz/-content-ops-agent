"""Per-user LLM budget guard on the endpoints that spend provider credit.

The limiter is a *cost* control, not an authorization boundary, so the contract
has two halves and both are asserted here:

1. It counts, per user, within a one-minute window, and returns 429 with a
   Retry-After header once the limit is exceeded.
2. It fails **open**. A rate-limit lookup that raises must not turn a database
   hiccup into a total outage of the LLM endpoints.

The guard is disabled when ``LLM_RATE_LIMIT_PER_MINUTE`` is 0, which is the
default outside production, so the rest of the suite never depends on wall-clock
windows.
"""

from __future__ import annotations

import pytest

from src.api import dependencies
from src.api.dependencies import enforce_llm_budget
from src.utils import config

pytestmark = pytest.mark.usefixtures("store")


class _Request:
    """Minimal stand-in for a Starlette Request carrying an authenticated user."""

    def __init__(self, user_id: str = "11111111111111111111111111111111") -> None:
        self.state = type("State", (), {"user": {"id": user_id, "username": "fixture_user"}})()


def test_guard_is_a_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "LLM_RATE_LIMIT_PER_MINUTE", 0)
    # No store is configured for _Request; if the guard did work it would raise.
    for _ in range(50):
        enforce_llm_budget(_Request())


def test_guard_allows_up_to_the_limit_then_returns_429(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(config, "LLM_RATE_LIMIT_PER_MINUTE", 3)
    for _ in range(3):
        enforce_llm_budget(_Request())

    with pytest.raises(HTTPException) as excinfo:
        enforce_llm_budget(_Request())

    assert excinfo.value.status_code == 429
    assert excinfo.value.headers["Retry-After"] == "60"


def test_guard_counts_each_user_separately(monkeypatch):
    monkeypatch.setattr(config, "LLM_RATE_LIMIT_PER_MINUTE", 2)
    first = _Request("11111111111111111111111111111111")

    enforce_llm_budget(first)
    enforce_llm_budget(first)

    # A different user has their own budget; one user's burst must not throttle
    # anyone else.
    enforce_llm_budget(_Request("33333333333333333333333333333333"))


def test_guard_fails_open_when_the_lookup_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_RATE_LIMIT_PER_MINUTE", 5)

    def boom(*args, **kwargs):
        raise RuntimeError("database is unavailable")

    monkeypatch.setattr(dependencies.AccountStore, "check_rate_limit", boom)

    # Must not raise: the LLM endpoint should stay reachable.
    enforce_llm_budget(_Request())


def test_guard_still_requires_authentication(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(config, "LLM_RATE_LIMIT_PER_MINUTE", 5)

    class Anonymous:
        state = type("State", (), {"user": None})()

    with pytest.raises(HTTPException) as excinfo:
        enforce_llm_budget(Anonymous())

    assert excinfo.value.status_code == 401


def test_llm_spending_routes_declare_the_guard():
    """Regression: a new LLM-spending route must not silently skip the guard."""
    from src.api.routes import agent, content

    guarded = set()
    for module in (agent.router, content.router):
        for route in module.routes:
            for dependency in getattr(route, "dependencies", []) or []:
                guarded.add(getattr(dependency, "dependency", None))
            for param in getattr(getattr(route, "endpoint", None), "__defaults__", ()) or []:
                guarded.add(getattr(param, "dependency", None))

    assert enforce_llm_budget in guarded, "no route declared enforce_llm_budget"
