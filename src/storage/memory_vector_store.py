"""ChromaDB vector store for long-term agent memory."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


class MemoryVectorStore:
    """Thin wrapper around a single ChromaDB collection for memory embeddings."""

    def __init__(self, persist_dir: str = "data/chroma"):
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="agent_memories",
            metadata={"hnsw:space": "cosine"},
        )
        self._embeddings = None

    @property
    def embeddings(self):
        if self._embeddings is None:
            from src.utils.embeddings import get_embeddings
            self._embeddings = get_embeddings()
        return self._embeddings

    def add(self, memory_id: str, content: str, category: str) -> None:
        embedding = self.embeddings.embed_query(content)
        self.collection.upsert(
            ids=[memory_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[{"category": category}],
        )

    def query(
        self,
        text: str,
        n_results: int = 5,
        category: str | None = None,
        threshold: float = 0.35,
    ) -> list[dict[str, Any]]:
        embedding = self.embeddings.embed_query(text)
        where = {"category": category} if category else None
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        items = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for i, mid in enumerate(ids):
            similarity = 1.0 - distances[i]
            if similarity < threshold:
                continue
            items.append({
                "id": mid,
                "content": docs[i],
                "category": metas[i].get("category", ""),
                "similarity": round(similarity, 4),
            })
        return items

    def delete(self, memory_id: str) -> None:
        try:
            self.collection.delete(ids=[memory_id])
        except Exception:
            pass

    def count(self) -> int:
        return self.collection.count()
