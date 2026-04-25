"""LiteLLM-based unified LLM client."""
from __future__ import annotations

from typing import Any

from src.utils import config


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
            raise RuntimeError("litellm is not installed. Run pip install -r requirements.txt") from exc

        provider = provider.lower()
        api_key = self._api_key(provider)
        if not api_key:
            raise ValueError(f"Missing API key for provider: {provider}")

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

        response = await litellm.acompletion(**request)
        return response.choices[0].message.content or ""

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
        raise ValueError(f"Unsupported provider: {provider}")
