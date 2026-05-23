import time

import httpx
from fastapi import APIRouter

from src.api.schemas.models import ModelInfo, ProviderInfo
from src.utils import config


router = APIRouter()


PROVIDER_MODELS = {
    "claude": [
        ("claude-opus-4-1-20250805", "Claude Opus 4.1"),
        ("claude-sonnet-4-20250514", "Claude Sonnet 4"),
        ("claude-3-7-sonnet-20250219", "Claude Sonnet 3.7"),
        ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet"),
        ("claude-3-5-haiku-20241022", "Claude Haiku 3.5"),
    ],
    "siliconflow": [
        ("zai-org/GLM-4.5-Air", "GLM-4.5 Air"),
        ("Qwen/Qwen2.5-7B-Instruct", "Qwen2.5 7B Instruct"),
        ("Qwen/Qwen2.5-14B-Instruct", "Qwen2.5 14B Instruct"),
        ("Qwen/Qwen2.5-32B-Instruct", "Qwen2.5 32B Instruct"),
        ("Qwen/Qwen2.5-72B-Instruct", "Qwen2.5 72B Instruct"),
    ],
    "deepseek": [
        ("deepseek-v4-flash", "DeepSeek V4 Flash"),
        ("deepseek-v4-pro", "DeepSeek V4 Pro"),
    ],
    "moonshot": [
        ("kimi-k2.6", "Kimi K2.6"),
        ("kimi-k2.5", "Kimi K2.5"),
        ("kimi-k2-turbo-preview", "Kimi K2 Turbo Preview"),
        ("kimi-k2-thinking", "Kimi K2 Thinking"),
        ("moonshot-v1-8k", "Moonshot V1 8K"),
        ("moonshot-v1-32k", "Moonshot V1 32K"),
        ("moonshot-v1-128k", "Moonshot V1 128K"),
    ],
    "newapi": [],
}

MODEL_CACHE_TTL_SECONDS = 300
_provider_model_cache: dict[str, tuple[float, list[ModelInfo]]] = {}


def provider_display_name(provider: str) -> str:
    if provider == "siliconflow":
        return "SiliconFlow"
    if provider == "deepseek":
        return "DeepSeek"
    if provider == "newapi":
        return "NewAPI"
    return provider.title()


def fallback_models(provider: str) -> list[ModelInfo]:
    return [
        ModelInfo(id=model_id, name=name)
        for model_id, name in PROVIDER_MODELS.get(provider, [])
    ]


async def fetch_siliconflow_models() -> list[ModelInfo] | None:
    if not config.SILICONFLOW_API_KEY:
        return None

    try:
        response = await get_json_with_cache(
            cache_key="siliconflow",
            url=f"{config.SILICONFLOW_BASE_URL.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"},
            params={"type": "text", "sub_type": "chat"},
        )
    except httpx.HTTPError:
        return None

    return cache_provider_models("siliconflow", parse_model_items(response.get("data", [])))


async def get_json_with_cache(
    cache_key: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, str | int] | None = None,
) -> dict:
    cached = _provider_model_cache.get(cache_key)
    if cached and time.time() - cached[0] < MODEL_CACHE_TTL_SECONDS:
        return {"data": [model.model_dump() for model in cached[1]]}

    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


def parse_model_items(items: list[dict]) -> list[ModelInfo] | None:
    models = sorted(
        {
            item["id"]: ModelInfo(
                id=item["id"],
                name=item.get("display_name") or item.get("name") or item["id"],
            )
            for item in items
            if isinstance(item, dict) and item.get("id")
        }.values(),
        key=lambda model: model.id.lower(),
    )
    return models or None


def cache_provider_models(provider: str, models: list[ModelInfo] | None) -> list[ModelInfo] | None:
    if models:
        _provider_model_cache[provider] = (time.time(), models)
    return models


async def fetch_anthropic_models() -> list[ModelInfo] | None:
    if not config.ANTHROPIC_API_KEY:
        return None

    cached = _provider_model_cache.get("claude")
    if cached and time.time() - cached[0] < MODEL_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                params={"limit": 1000},
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    return cache_provider_models("claude", parse_model_items(response.json().get("data", [])))


async def fetch_openai_compatible_models(provider: str, base_url: str, api_key: str | None) -> list[ModelInfo] | None:
    if not api_key:
        return None

    cached = _provider_model_cache.get(provider)
    if cached and time.time() - cached[0] < MODEL_CACHE_TTL_SECONDS:
        return cached[1]

    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        urls = [f"{trimmed}/models", f"{trimmed[:-3].rstrip('/')}/models"]
    else:
        # Some gateways (e.g. NewAPI) accept chat completions at the root but
        # only expose the model catalogue under /v1. Probe /v1/models first.
        urls = [f"{trimmed}/v1/models", f"{trimmed}/models"]

    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
                response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            # ValueError covers JSONDecodeError when the gateway returns HTML/empty.
            continue
        return cache_provider_models(provider, parse_model_items(payload.get("data", [])))
    return None


async def fetch_provider_models(provider: str) -> list[ModelInfo] | None:
    if provider == "claude":
        return await fetch_anthropic_models()
    if provider == "siliconflow":
        return await fetch_siliconflow_models()
    if provider == "deepseek":
        return await fetch_openai_compatible_models(provider, config.DEEPSEEK_BASE_URL, config.DEEPSEEK_API_KEY)
    if provider == "moonshot":
        return await fetch_openai_compatible_models(provider, config.MOONSHOT_BASE_URL, config.MOONSHOT_API_KEY)
    if provider == "newapi":
        if not config.NEWAPI_BASE_URL:
            return None
        return await fetch_openai_compatible_models(provider, config.NEWAPI_BASE_URL, config.NEWAPI_API_KEY)
    return None


@router.get("", response_model=list[ProviderInfo])
async def list_models() -> list[ProviderInfo]:
    providers: list[ProviderInfo] = []
    for provider in config.get_supported_providers():
        dynamic_models = await fetch_provider_models(provider)
        providers.append(
            ProviderInfo(
                id=provider,
                name=provider_display_name(provider),
                configured=config.has_provider_key(provider),
                default_model=config.get_model(provider),
                models=dynamic_models or fallback_models(provider),
            )
        )
    return providers
