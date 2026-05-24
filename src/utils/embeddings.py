"""Singleton embedding model for the memory vector store."""
from __future__ import annotations

from functools import lru_cache

from src.utils.config import Config as config


@lru_cache(maxsize=1)
def get_embeddings():
    from langchain_community.embeddings import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=config.MEMORY_EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
    )
