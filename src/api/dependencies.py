"""Share the database pool while binding request stores and file memory to one user."""

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
