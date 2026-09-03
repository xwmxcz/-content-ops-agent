"""LiteLLM-based unified LLM client."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator

from src.utils import config


class LLMClientError(RuntimeError):
    """Base error for LLM client failures safe enough for API mapping."""


class LLMConfigurationError(ValueError):
    """Raised when provider configuration is invalid or incomplete."""


class LLMGenerationError(LLMClientError):
    """Raised when an LLM request fails after validation."""


@dataclass
class StreamChunk:
    """One streaming chunk emitted by LiteLLMClient.generate_stream.

    `delta` is the incremental text since the last chunk (may be empty).
    `usage` is set only on the final chunk: tuple of (prompt_tokens, completion_tokens).
    """
    delta: str = ""
    usage: tuple[int, int] | None = None


class LiteLLMClient:
    """Small adapter around LiteLLM's async completion API."""

    async def generate(
        self,
        provider: str,
        model: str | None,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """One-shot completion.

        ``response_format`` is forwarded to the provider when set (JSON mode for the
        OpenAI-compatible gateways). A provider that rejects the parameter raises
        during the call, so callers that opt in must be able to retry without it;
        see ``DynamicPipeline._call_planner``.
        """
        try:
            import litellm
        except ImportError as exc:
            raise LLMGenerationError("LLM dependency is not installed") from exc
        # Mute the "Give Feedback / Get Help: https://github.com/BerriAI/litellm/..."
        # footer litellm appends to every exception's str(). It's not actionable for
        # end users and shows up in our SSE step_failed events. Real error text is
        # still preserved via _format_provider_error.
        litellm.suppress_debug_info = True

        provider = provider.lower()
        api_key = self._api_key(provider)
        if not api_key:
            raise LLMConfigurationError(f"Missing API key for provider: {provider}")

        request: dict[str, Any] = {
            "model": config.get_litellm_model(provider, model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_key": api_key,
        }
        api_base = config.get_provider_api_base(provider)
        if api_base:
            request["api_base"] = api_base
        if response_format:
            request["response_format"] = response_format

        try:
            response = await asyncio.wait_for(
                litellm.acompletion(**request),
                timeout=config.LLM_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise LLMGenerationError(
                f"LLM request timed out after {config.LLM_TIMEOUT_SECONDS:g} seconds"
            ) from exc
        except Exception as exc:
            raise LLMGenerationError(_format_provider_error(provider, exc)) from exc

        content = response.choices[0].message.content or ""
        if not content.strip():
            raise LLMGenerationError("LLM returned an empty response")
        return content

    async def generate_from_prompts(
        self,
        provider: str,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        return await self.generate(
            provider=provider,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    async def generate_stream(
        self,
        provider: str,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> AsyncIterator[StreamChunk]:
        """Async iterator yielding StreamChunk objects.

        Falls back to a single non-streaming chunk if the provider rejects
        streaming. Final chunk carries usage when the provider includes it.
        """
        try:
            import litellm
        except ImportError as exc:
            raise LLMGenerationError("LLM dependency is not installed") from exc
        litellm.suppress_debug_info = True

        provider = provider.lower()
        api_key = self._api_key(provider)
        if not api_key:
            raise LLMConfigurationError(f"Missing API key for provider: {provider}")

        request: dict[str, Any] = {
            "model": config.get_litellm_model(provider, model),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_key": api_key,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        api_base = config.get_provider_api_base(provider)
        if api_base:
            request["api_base"] = api_base

        try:
            response = await litellm.acompletion(**request)
        except Exception as exc:
            # Stream not supported → fall back to one-shot
            import sys
            print(
                f"[litellm.stream] open failed, falling back to non-stream: "
                f"{type(exc).__name__}: {_format_provider_error(provider, exc)}",
                file=sys.stderr,
                flush=True,
            )
            text = await self.generate_from_prompts(
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            yield StreamChunk(delta=text, usage=None)
            return

        prompt_tokens = 0
        completion_tokens = 0
        accumulated = ""
        try:
            async for raw in response:
                delta_text = ""
                try:
                    choice = raw.choices[0]
                    delta_obj = getattr(choice, "delta", None) or {}
                    delta_text = getattr(delta_obj, "content", "") or (
                        delta_obj.get("content", "") if isinstance(delta_obj, dict) else ""
                    ) or ""
                except (AttributeError, IndexError, KeyError):
                    delta_text = ""
                usage = getattr(raw, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or prompt_tokens
                    completion_tokens = getattr(usage, "completion_tokens", 0) or completion_tokens
                if delta_text:
                    accumulated += delta_text
                    yield StreamChunk(delta=delta_text)
        except Exception as exc:
            import sys
            print(
                f"[litellm.stream] iteration failed: {type(exc).__name__}: {exc} "
                f"(accumulated={len(accumulated)} chars)",
                file=sys.stderr,
                flush=True,
            )
            # Mid-stream failure with usable partial output → swallow and finish gracefully.
            # Common cause: provider closes the stream when max_tokens is reached without
            # emitting a clean finish_reason=length frame.
            if accumulated.strip():
                yield StreamChunk(delta="", usage=(prompt_tokens, completion_tokens))
                return
            # Nothing usable yet → fall back to one-shot non-streaming request.
            try:
                text = await self.generate_from_prompts(
                    provider=provider,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as fallback_exc:
                raise LLMGenerationError(
                    f"LLM streaming failed: {type(exc).__name__}: {exc}"
                ) from fallback_exc
            yield StreamChunk(delta=text, usage=None)
            return
        yield StreamChunk(delta="", usage=(prompt_tokens, completion_tokens))

    @staticmethod
    def _api_key(provider: str) -> str | None:
        if provider == "claude":
            return config.ANTHROPIC_API_KEY
        if provider == "siliconflow":
            return config.SILICONFLOW_API_KEY
        if provider == "deepseek":
            return config.DEEPSEEK_API_KEY
        if provider == "moonshot":
            return config.MOONSHOT_API_KEY
        if provider == "newapi":
            return config.NEWAPI_API_KEY
        raise LLMConfigurationError(f"Unsupported provider: {provider}")


def _format_provider_error(provider: str, exc: BaseException) -> str:
    """Distil litellm/provider exceptions into a single human-readable line.

    litellm wraps upstream errors in `APIError` whose `str()` contains the upstream
    body but is buried under a "Give Feedback / Get Help" footer (already muted via
    `suppress_debug_info`). For NewAPI specifically, the upstream JSON body holds
    the only useful diagnostic ("model_not_found", "No active API keys", etc.) so
    we prefer that over the litellm wrapping.
    """
    import re

    raw = str(exc) or exc.__class__.__name__

    # Try the upstream JSON error body first (NewAPI / OpenAI gateways embed it).
    # Brace-count so we handle nested objects like {"error":{...}} correctly —
    # a regex with non-greedy .*? would stop at the first inner `}`.
    start = raw.find('{"error"')
    if start != -1:
        depth = 0
        end = -1
        for idx, ch in enumerate(raw[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        if end != -1:
            try:
                import json
                body = json.loads(raw[start:end])
                msg = (body.get("error") or {}).get("message") or ""
                if msg:
                    status_match = re.search(r"status code: (\d+)", raw)
                    status = f"HTTP {status_match.group(1)} " if status_match else ""
                    return f"{provider}: {status}{msg.strip()}"
            except (ValueError, TypeError):
                pass

    # Fall back to the first non-empty line, stripping the litellm wrapping prefix
    # so users see "openai_error" instead of "litellm.APIError: APIError: OpenAIException - openai_error".
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(
            r"^litellm\.[A-Za-z]+Error:\s*[A-Za-z]+Error:\s*[A-Za-z]+Exception\s*-\s*",
            "",
            line,
        )
        return f"{provider}: {cleaned}"
    return f"{provider}: {exc.__class__.__name__}"
