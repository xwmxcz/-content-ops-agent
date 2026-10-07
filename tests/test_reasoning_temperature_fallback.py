"""Reasoning models reject `temperature` and the client must retry without it.

The failure this pins down is specific and was seen in production: reasoning
models behind an OpenAI-compatible gateway (NewAPI and friends) accept only
`temperature=1` while reasoning is active. litellm enforces that **client-side**,
so the request never leaves the process and the step fails permanently.

It bit the non-tool sub-agents only, because those carry fixed per-step
temperatures (strategy 0.5, writer 0.85, editor 0.5) and reach the provider via
litellm, while the tool-using agents go through LangChain's `ChatOpenAI`, which
performs no such check. The asymmetry is why research and fact-checking
succeeded while strategy, drafting, and polishing all failed.

Two properties matter here, and the second is the easy one to get wrong:

1. A rejected temperature is retried once with the parameter dropped.
2. Every *other* unsupported-parameter failure still surfaces. A blanket
   `litellm.drop_params = True` would have fixed (1) while silently discarding
   genuinely wrong arguments, so that is deliberately not the implementation.
"""

from __future__ import annotations

import sys
import types

import pytest

from src.llm import litellm_client
from src.llm.litellm_client import LiteLLMClient, LLMGenerationError
from src.utils import config

pytestmark = pytest.mark.usefixtures("configured_newapi")


class _Message:
    def __init__(self, content: str = "OK") -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str = "OK") -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str = "OK") -> None:
        self.choices = [_Choice(content)]


def _unsupported_params_error() -> Exception:
    """Mirror litellm's own exception type name, which is what the retry matches on."""
    error_type = type("UnsupportedParamsError", (Exception,), {})
    return error_type(
        "gpt-6.1-sol doesn't support temperature=0.5 while reasoning is active. "
        "Only temperature=1 is supported unless reasoning_effort resolves to 'none'."
    )


@pytest.fixture
def configured_newapi(monkeypatch):
    monkeypatch.setattr(config, "NEWAPI_API_KEY", "test-key")
    monkeypatch.setattr(config, "NEWAPI_BASE_URL", "https://gateway.example.com")
    monkeypatch.setattr(config, "NEWAPI_MODEL", "gpt-6.1-sol")


def _install_fake_litellm(monkeypatch, impl):
    """Install a stub `litellm` module, since the client imports it lazily."""
    module = types.ModuleType("litellm")
    module.suppress_debug_info = False
    module.acompletion = impl
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def test_generate_retries_without_temperature(monkeypatch):
    """The regression: a rejected temperature must not fail the step."""
    seen: list[dict] = []

    async def acompletion(**kwargs):
        seen.append(kwargs)
        if "temperature" in kwargs:
            raise _unsupported_params_error()
        return _Response("retried-ok")

    _install_fake_litellm(monkeypatch, acompletion)

    import asyncio

    result = asyncio.run(
        LiteLLMClient().generate_from_prompts(
            provider="newapi",
            model="gpt-6.1-sol",
            system_prompt="s",
            user_prompt="u",
            temperature=0.5,  # the strategy agent's value
            max_tokens=32,
        )
    )

    assert result == "retried-ok"
    assert len(seen) == 2, "expected exactly one retry"
    assert seen[0]["temperature"] == 0.5
    assert "temperature" not in seen[1], "retry must drop the rejected parameter"
    # Everything else survives the retry.
    assert seen[1]["model"] == seen[0]["model"]
    assert seen[1]["max_tokens"] == seen[0]["max_tokens"]


@pytest.mark.parametrize("temperature", [0.3, 0.5, 0.85])
def test_every_fixed_step_temperature_recovers(monkeypatch, temperature):
    """All three failing step temperatures recover, not just one."""
    calls = {"n": 0}

    async def acompletion(**kwargs):
        calls["n"] += 1
        if "temperature" in kwargs:
            raise _unsupported_params_error()
        return _Response("ok")

    _install_fake_litellm(monkeypatch, acompletion)

    import asyncio

    result = asyncio.run(
        LiteLLMClient().generate_from_prompts(
            provider="newapi",
            model="gpt-6.1-sol",
            system_prompt="s",
            user_prompt="u",
            temperature=temperature,
            max_tokens=32,
        )
    )
    assert result == "ok"
    assert calls["n"] == 2


def test_generate_succeeds_without_any_retry_when_temperature_is_accepted(monkeypatch):
    """Temperature=1 models must not pay for a retry they do not need."""
    calls = {"n": 0}

    async def acompletion(**kwargs):
        calls["n"] += 1
        return _Response("first-try-ok")

    _install_fake_litellm(monkeypatch, acompletion)

    import asyncio

    result = asyncio.run(
        LiteLLMClient().generate_from_prompts(
            provider="newapi",
            model="gpt-6.1-sol",
            system_prompt="s",
            user_prompt="u",
            temperature=1.0,
            max_tokens=32,
        )
    )
    assert result == "first-try-ok"
    assert calls["n"] == 1


def test_other_unsupported_parameters_still_fail(monkeypatch):
    """A blanket drop_params would hide real mistakes; only temperature is forgiven."""
    calls = {"n": 0}

    async def acompletion(**kwargs):
        calls["n"] += 1
        error_type = type("UnsupportedParamsError", (Exception,), {})
        raise error_type("gpt-6.1-sol doesn't support response_format=x")

    _install_fake_litellm(monkeypatch, acompletion)

    import asyncio

    with pytest.raises(LLMGenerationError):
        asyncio.run(
            LiteLLMClient().generate_from_prompts(
                provider="newapi",
                model="gpt-6.1-sol",
                system_prompt="s",
                user_prompt="u",
                temperature=0.5,
                max_tokens=32,
            )
        )
    assert calls["n"] == 1, "an unrelated UnsupportedParamsError must not be retried"


def test_unrelated_errors_do_not_trigger_a_retry(monkeypatch):
    """Only the temperature rejection is retried; other failures pass straight through."""
    calls = {"n": 0}

    async def acompletion(**kwargs):
        calls["n"] += 1
        raise RuntimeError("connection reset")

    _install_fake_litellm(monkeypatch, acompletion)

    import asyncio

    with pytest.raises(LLMGenerationError):
        asyncio.run(
            LiteLLMClient().generate_from_prompts(
                provider="newapi",
                model="gpt-6.1-sol",
                system_prompt="s",
                user_prompt="u",
                temperature=0.5,
                max_tokens=32,
            )
        )
    assert calls["n"] == 1


def test_unsupported_temperature_detection_is_narrow():
    """The predicate keys off both the exception type name and the message."""
    assert litellm_client._is_unsupported_temperature(_unsupported_params_error())
    # Right message, wrong type.
    assert not litellm_client._is_unsupported_temperature(RuntimeError("temperature is bad"))
    # Right type, wrong cause.
    other = type("UnsupportedParamsError", (Exception,), {})
    assert not litellm_client._is_unsupported_temperature(other("bad response_format"))
