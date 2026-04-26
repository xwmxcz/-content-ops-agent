"""Content generation helpers for the API layer."""
from __future__ import annotations

import re
from datetime import datetime

from src.api.schemas.content import GenerateRequest, RefineRequest, SeoRequest, TitleRequest
from src.llm.litellm_client import LiteLLMClient
from src.models import ContentStyle, ContentType, GeneratedContent
from src.storage import ContentStore
from src.tools.prompt_templates import PromptTemplates
from src.utils import config


def resolve_provider(provider: str | None) -> str:
    resolved = (provider or config.LLM_PROVIDER).lower()
    if resolved not in config.get_supported_providers():
        raise ValueError(f"Unknown provider: {resolved}")
    return resolved


def build_generation_prompts(request: GenerateRequest) -> tuple[str, str]:
    templates = PromptTemplates()
    system_prompt = templates.get_system_prompt(request.content_type, request.style)

    if request.content_type == ContentType.XIAOHONGSHU:
        user_prompt = templates.get_xiaohongshu_prompt(request.topic, request.keywords, request.length)
    elif request.content_type == ContentType.WEIBO:
        user_prompt = templates.get_weibo_prompt(request.topic, request.keywords)
    elif request.content_type == ContentType.BLOG:
        user_prompt = templates.get_blog_prompt(request.topic, request.keywords, request.length)
    elif request.content_type == ContentType.VIDEO_SCRIPT:
        user_prompt = templates.get_video_script_prompt(request.topic, request.length)
    elif request.content_type == ContentType.TWITTER:
        keywords = f"\nKeywords: {', '.join(request.keywords)}" if request.keywords else ""
        user_prompt = (
            f"Create a concise Twitter/X post about: {request.topic}.\n"
            "Keep it clear, punchy, and suitable for social sharing."
            f"{keywords}"
        )
    else:
        raise ValueError(f"Unsupported content type: {request.content_type}")

    return system_prompt, user_prompt


def parse_generated_content(content_text: str, content_type: ContentType) -> GeneratedContent:
    title = None
    normalized = content_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    content = normalized
    tags = None

    title_match = re.search(r"【\s*标题\s*】\s*\n(.+?)(?:\n|$)", normalized)
    if title_match:
        title = title_match.group(1).strip()

    body_match = re.search(
        r"【\s*(?:正文|脚本)\s*】\s*\n(.*?)(?=\n?【\s*标签\s*】|$)",
        normalized,
        re.DOTALL,
    )
    if body_match:
        content = body_match.group(1).strip()
    elif title_match:
        content = normalized[title_match.end():].strip()

    tags_match = re.search(r"【\s*标签\s*】\s*\n(.+?)\s*$", normalized, re.DOTALL)
    if tags_match:
        tags_text = tags_match.group(1).strip()
        tags = [tag.strip() for tag in re.split(r"[,，\s]+", tags_text) if tag.strip()]

    return GeneratedContent(
        title=title,
        content=content,
        tags=tags,
        content_type=content_type,
        metadata={"raw_response": content_text},
    )


async def generate_content(
    request: GenerateRequest,
    llm: LiteLLMClient,
    store: ContentStore,
) -> tuple[int, GeneratedContent, str, str]:
    provider = resolve_provider(request.provider)
    system_prompt, user_prompt = build_generation_prompts(request)
    content_text = await llm.generate_from_prompts(
        provider=provider,
        model=request.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    result = parse_generated_content(content_text, request.content_type)
    content_id = store.save_content(
        result,
        llm_provider=provider,
        model_name=config.get_litellm_model(provider, request.model),
        style=request.style.value,
        keywords=request.keywords,
    )
    return content_id, result, provider, config.get_litellm_model(provider, request.model)


async def refine_content(
    request: RefineRequest,
    llm: LiteLLMClient,
    store: ContentStore,
) -> tuple[int, GeneratedContent, str, str]:
    original = store.get_content(request.content_id)
    if not original:
        raise LookupError(f"Content {request.content_id} was not found")

    provider = resolve_provider(request.provider)
    style_instruction = ""
    if request.new_style:
        style_instruction = f" Rewrite it in a {request.new_style.value} style."
    instruction = request.instruction or "Improve clarity, structure, and readability."

    system_prompt = "You are a professional content editor. Preserve the core message while improving the draft."
    user_prompt = (
        f"Instruction: {instruction}{style_instruction}\n\n"
        f"Original content:\n{original['content']}\n\n"
        "Return only the refined content."
    )
    refined_text = await llm.generate_from_prompts(
        provider=provider,
        model=request.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    refined = GeneratedContent(
        content=refined_text,
        title=original.get("title"),
        tags=original.get("tags"),
        content_type=ContentType(original["content_type"]),
        created_at=datetime.now(),
    )
    new_id = store.save_content(
        refined,
        llm_provider=provider,
        model_name=config.get_litellm_model(provider, request.model),
        parent_id=request.content_id,
        style=original.get("style", "casual"),
        keywords=original.get("keywords", []),
    )
    update_fields = {"status": "refined"}
    if request.new_style:
        update_fields["style"] = request.new_style.value
    store.update_content(new_id, **update_fields)
    return new_id, refined, provider, config.get_litellm_model(provider, request.model)


async def generate_titles(request: TitleRequest, llm: LiteLLMClient, store: ContentStore) -> str:
    provider = resolve_provider(request.provider)
    topic = request.topic
    source = ""
    if request.content_id:
        content = store.get_content(request.content_id)
        if not content:
            raise LookupError(f"Content {request.content_id} was not found")
        topic = topic or content.get("title") or content["content"][:80]
        source = f"\nSource content:\n{content['content'][:800]}"
    if not topic:
        raise ValueError("Either topic or content_id is required")

    return await llm.generate_from_prompts(
        provider=provider,
        model=request.model,
        system_prompt="You are an expert headline writer.",
        user_prompt=(
            f"Create {request.count} compelling title options for {request.content_type.value}.\n"
            f"Topic: {topic}{source}\n"
            "Return a numbered list only."
        ),
        temperature=0.9,
        max_tokens=1024,
    )


async def analyze_seo(request: SeoRequest, llm: LiteLLMClient, store: ContentStore) -> str:
    content = store.get_content(request.content_id)
    if not content:
        raise LookupError(f"Content {request.content_id} was not found")
    provider = resolve_provider(request.provider)
    return await llm.generate_from_prompts(
        provider=provider,
        model=request.model,
        system_prompt="You are an SEO specialist. Provide concise, actionable recommendations.",
        user_prompt=(
            f"Title: {content.get('title') or 'Untitled'}\n"
            f"Content:\n{content['content'][:1200]}\n\n"
            "Provide keyword suggestions, title improvements, structure improvements, and a meta description."
        ),
        temperature=0.5,
        max_tokens=2048,
    )
