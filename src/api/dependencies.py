"""Share the database pool while binding request stores and file memory to one user."""

import logging
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException, Request

from src.agent.context_compressor import ContextCompressor
from src.agent.context_engine import ContextEngine
from src.agent.memory_curator import MemoryCurator
from src.api.services.chat_agent import ChatAgentService
from src.api.services.publish_service import PublishService, create_publish_service
from src.llm.litellm_client import LiteLLMClient
from src.storage import ContentStore
from src.storage.account_store import AccountStore
from src.storage.file_memory import FileMemory
from src.storage.schema import assert_schema_current
from src.utils import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_system_store() -> ContentStore:
    store = ContentStore(
        database_url=config.DATABASE_URL,
        initialize_schema=config.SCHEMA_MANAGEMENT == "create",
    )
    if config.SCHEMA_MANAGEMENT == "validate":
        try:
            assert_schema_current(store.engine)
        except Exception:
            store.engine.dispose()
            raise
    return store


def get_account_store() -> AccountStore:
    return AccountStore(get_system_store())


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def get_store(request: Request) -> ContentStore:
    return get_system_store().for_user(get_current_user(request)["id"])


def enforce_llm_budget(request: Request) -> None:
    """Throttle one authenticated user's calls to LLM-spending endpoints.

    Auth endpoints had a limiter; nothing bounded an authenticated user looping
    the chat or agent-run endpoints, which is the path that can drain the
    operator's provider account. Keyed by user id rather than peer address: the
    caller is identified and authenticated, and the cost is charged to that
    account, not to a shared NAT address.

    Disabled when ``LLM_RATE_LIMIT_PER_MINUTE`` is 0 (the local/test default) so
    the suite never depends on wall-clock windows. A store failure fails *open*,
    deliberately: refusing every LLM call because the rate-limit row could not be
    written would turn a database hiccup into a total outage. The limiter is a
    cost control, not an authorization boundary.
    """
    limit = config.LLM_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    user = get_current_user(request)
    try:
        allowed = AccountStore(get_system_store()).check_rate_limit("llm", user["id"], limit=limit, seconds=60)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 -- limiter is cost control, not authz; fail open
        logger.warning("llm rate-limit check failed, allowing request: %s", exc.__class__.__name__)
        return
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": "60"},
        )


@lru_cache(maxsize=128)
def _file_memory_for(user_id: str) -> FileMemory | None:
    if not config.MEMORY_ENABLED:
        return None
    return FileMemory(
        dir=Path(config.MEMORY_DIR) / user_id,
        memory_limit=config.MEMORY_MD_LIMIT,
        user_limit=config.USER_MD_LIMIT,
    )


def get_file_memory(request: Request) -> FileMemory | None:
    return _file_memory_for(get_current_user(request)["id"])


@lru_cache(maxsize=1)
def get_context_engine() -> ContextEngine | None:
    if not config.CONTEXT_COMPRESS_ENABLED:
        return None
    return ContextCompressor(
        aux_llm=LiteLLMClient(),
        trigger_messages=config.CONTEXT_COMPRESS_TRIGGER_MESSAGES,
        keep_head=config.CONTEXT_COMPRESS_KEEP_HEAD,
        keep_tail=config.CONTEXT_COMPRESS_KEEP_TAIL,
    )


def get_memory_curator(request: Request) -> MemoryCurator | None:
    fm = get_file_memory(request)
    if fm is None or not config.MEMORY_CURATOR_ENABLED:
        return None
    return MemoryCurator(
        aux_llm=LiteLLMClient(),
        file_memory=fm,
        min_messages=config.MEMORY_CURATOR_MIN_MESSAGES,
        max_actions=config.MEMORY_CURATOR_MAX_ACTIONS,
    )


def get_litellm_client() -> LiteLLMClient:
    return LiteLLMClient()


def get_chat_agent_service(
    store: ContentStore = Depends(get_store),
    file_memory: FileMemory | None = Depends(get_file_memory),
) -> ChatAgentService:
    return ChatAgentService(
        store=store,
        file_memory=file_memory,
        context_engine=get_context_engine(),
    )


def get_publish_service(store: ContentStore = Depends(get_store)) -> PublishService:
    return create_publish_service(store)
