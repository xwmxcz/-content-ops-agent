"""REST API routes for memory management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.dependencies import get_memory_store, get_store
from src.storage import ContentStore
from src.storage.memory_vector_store import MemoryVectorStore
from src.utils import config

router = APIRouter()


class MemoryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    category: str = Field(default="fact", pattern=r"^(preference|fact|context|instruction)$")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, pattern=r"^(preference|fact|context|instruction)$")
    importance: float | None = Field(default=None, ge=0.0, le=1.0)


class MemoryResponse(BaseModel):
    id: str
    content: str
    category: str
    importance: float
    access_count: int = 0
    last_used_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@router.get("", response_model=list[MemoryResponse])
def list_memories(
    category: str | None = None,
    limit: int = 50,
    store: ContentStore = Depends(get_store),
):
    return store.list_memories(category=category, limit=limit)


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    req: MemoryCreateRequest,
    store: ContentStore = Depends(get_store),
    memory_store: MemoryVectorStore | None = Depends(get_memory_store),
):
    from uuid import uuid4
    memory_id = f"mem_{uuid4().hex[:16]}"
    result = store.save_memory(
        memory_id=memory_id,
        content=req.content,
        category=req.category,
        importance=req.importance,
    )
    if memory_store:
        memory_store.add(memory_id, req.content, req.category)
    return result


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory(
    memory_id: str,
    store: ContentStore = Depends(get_store),
):
    mem = store.get_memory(memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.put("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    req: MemoryUpdateRequest,
    store: ContentStore = Depends(get_store),
    memory_store: MemoryVectorStore | None = Depends(get_memory_store),
):
    existing = store.get_memory(memory_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")
    content = req.content if req.content is not None else existing["content"]
    category = req.category if req.category is not None else existing["category"]
    importance = req.importance if req.importance is not None else existing["importance"]
    result = store.save_memory(
        memory_id=memory_id,
        content=content,
        category=category,
        importance=importance,
    )
    if memory_store:
        memory_store.delete(memory_id)
        memory_store.add(memory_id, content, category)
    return result


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: str,
    store: ContentStore = Depends(get_store),
    memory_store: MemoryVectorStore | None = Depends(get_memory_store),
):
    deleted = store.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    if memory_store:
        memory_store.delete(memory_id)


@router.get("/search/query")
def search_memories(
    q: str,
    category: str | None = None,
    limit: int = 10,
    store: ContentStore = Depends(get_store),
    memory_store: MemoryVectorStore | None = Depends(get_memory_store),
):
    results = []
    if memory_store:
        results = memory_store.query(
            text=q,
            n_results=limit,
            category=category,
            threshold=config.MEMORY_SIMILARITY_THRESHOLD,
        )
    if not results:
        results = store.search_memories_text(q, category=category, limit=limit)
    return {"memories": results, "count": len(results)}
