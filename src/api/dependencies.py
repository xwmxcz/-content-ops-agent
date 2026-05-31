"""FastAPI dependencies."""
from functools import lru_cache

from fastapi import Depends

from src.agent.context_compressor import ContextCompressor
from src.agent.context_engine import ContextEngine
from src.agent.memory_curator import MemoryCurator
from src.api.services.publish_service import PublishService, create_publish_service
from src.llm.litellm_client import LiteLLMClient
from src.api.services.chat_agent import ChatAgentService
from src.storage import ContentStore
from src.storage.file_memory import FileMemory
from src.utils import config


@lru_cache(maxsize=1)
def get_store() -> ContentStore:
    return ContentStore(database_url=config.DATABASE_URL)


@lru_cache(maxsize=1)
def get_file_memory() -> FileMemory | None:
    if not config.MEMORY_ENABLED:
        return None
    return FileMemory(
        dir=config.MEMORY_DIR,
        memory_limit=config.MEMORY_MD_LIMIT,
        user_limit=config.USER_MD_LIMIT,
    )


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


@lru_cache(maxsize=1)
def get_memory_curator() -> MemoryCurator | None:
    fm = get_file_memory()
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


def get_chat_agent_service(store: ContentStore = Depends(get_store)) -> ChatAgentService:
    return ChatAgentService(
        store=store,
        file_memory=get_file_memory(),
        context_engine=get_context_engine(),
    )


def get_publish_service(store: ContentStore = Depends(get_store)) -> PublishService:
    return create_publish_service(store)
