"""FastAPI dependencies."""
from functools import lru_cache

from src.llm.litellm_client import LiteLLMClient
from src.storage import ContentStore
from src.utils import config


@lru_cache(maxsize=1)
def get_store() -> ContentStore:
    return ContentStore(database_url=config.DATABASE_URL)


def get_litellm_client() -> LiteLLMClient:
    return LiteLLMClient()
