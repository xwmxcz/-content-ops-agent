"""FastAPI dependencies."""
from functools import lru_cache

from fastapi import Depends

from src.llm.litellm_client import LiteLLMClient
from src.api.services.chat_agent import ChatAgentService
from src.storage import ContentStore
from src.utils import config


@lru_cache(maxsize=1)
def get_store() -> ContentStore:
    return ContentStore(database_url=config.DATABASE_URL)


def get_litellm_client() -> LiteLLMClient:
    return LiteLLMClient()


def get_chat_agent_service(store: ContentStore = Depends(get_store)) -> ChatAgentService:
    return ChatAgentService(store=store)
