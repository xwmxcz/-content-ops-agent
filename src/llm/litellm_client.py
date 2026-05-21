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
    ) -> str:
        try:
            import litellm
        except ImportError as exc:
            raise LLMGenerationError("LLM dependency is not installed") from exc

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
            raise LLMGenerationError("LLM request failed") from exc

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
        }
        api_base = config.get_provider_api_base(provider)
        if api_base:
            request["api_base"] = api_base

        try:
            response = await litellm.acompletion(**request)
        except Exception as exc:
            # Stream not supported → fall back to one-shot
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
                    yield StreamChunk(delta=delta_text)
        except Exception as exc:
            raise LLMGenerationError("LLM streaming failed") from exc
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
        raise LLMConfigurationError(f"Unsupported provider: {provider}")
