"""FastAPI dependencies."""
from functools import lru_cache

from fastapi import Depends

from src.api.services.publish_service import PublishService, create_publish_service
from src.llm.litellm_client import LiteLLMClient
from src.api.services.chat_agent import ChatAgentService
from src.storage import ContentStore
from src.storage.memory_vector_store import MemoryVectorStore
from src.utils import config


@lru_cache(maxsize=1)
def get_store() -> ContentStore:
    return ContentStore(database_url=config.DATABASE_URL)


@lru_cache(maxsize=1)
def get_memory_store() -> MemoryVectorStore | None:
    if not config.MEMORY_ENABLED:
        return None
    return MemoryVectorStore(persist_dir=config.MEMORY_CHROMA_DIR)


def get_litellm_client() -> LiteLLMClient:
    return LiteLLMClient()


def get_chat_agent_service(store: ContentStore = Depends(get_store)) -> ChatAgentService:
    memory_store = get_memory_store()
    return ChatAgentService(store=store, memory_store=memory_store)


def get_publish_service(store: ContentStore = Depends(get_store)) -> PublishService:
    return create_publish_service(store)
