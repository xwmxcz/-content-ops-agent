"""REST API routes for the Hermes-style 4-layer memory system.

Endpoints (relative to `/api/memory`):

  GET  /agent              → read MEMORY.md (agent notes)
  PUT  /agent              → overwrite MEMORY.md
  GET  /user               → read USER.md (user profile)
  PUT  /user               → overwrite USER.md
  POST /search             → FTS5 search over agent_messages
  POST /refresh-snapshot   → drop the frozen per-thread system-prompt cache

The path was previously `/api/memories` (CRUD over `agent_memories` rows);
that mount has been retired together with the vector-backed memory.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.dependencies import get_file_memory, get_store
from src.api.services.chat_agent import ChatAgentService
from src.storage import ContentStore
from src.storage.file_memory import AGENT, FileMemory, MemoryLimitExceeded, USER


router = APIRouter()


# ─── Schemas ───────────────────────────────────────────────────────────────


class MemoryFile(BaseModel):
    content: str = Field(default="")
    char_count: int
    char_limit: int


class MemoryFileUpdate(BaseModel):
    content: str = Field(default="")


class SessionSearchRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=400)
    limit: int = Field(default=10, ge=1, le=50)
    thread_id: str | None = None


class SessionSearchResponse(BaseModel):
    messages: list[dict]
    count: int


class RefreshSnapshotRequest(BaseModel):
    thread_id: str | None = None


# ─── Helpers ───────────────────────────────────────────────────────────────


def _require_memory(file_memory: FileMemory | None) -> FileMemory:
    if file_memory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory subsystem disabled (MEMORY_ENABLED=false)",
        )
    return file_memory


def _stats(file_memory: FileMemory, target: str) -> dict:
    return file_memory.stats(target)


# ─── MEMORY.md (agent notes) ───────────────────────────────────────────────


@router.get("/agent", response_model=MemoryFile)
def read_agent_memory(file_memory: FileMemory | None = Depends(get_file_memory)):
    return _stats(_require_memory(file_memory), AGENT)


@router.put("/agent", response_model=MemoryFile)
def write_agent_memory(
    req: MemoryFileUpdate,
    file_memory: FileMemory | None = Depends(get_file_memory),
):
    fm = _require_memory(file_memory)
    try:
        fm.save(AGENT, req.content)
    except MemoryLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    return _stats(fm, AGENT)


# ─── USER.md (user profile) ────────────────────────────────────────────────


@router.get("/user", response_model=MemoryFile)
def read_user_memory(file_memory: FileMemory | None = Depends(get_file_memory)):
    return _stats(_require_memory(file_memory), USER)


@router.put("/user", response_model=MemoryFile)
def write_user_memory(
    req: MemoryFileUpdate,
    file_memory: FileMemory | None = Depends(get_file_memory),
):
    fm = _require_memory(file_memory)
    try:
        fm.save(USER, req.content)
    except MemoryLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    return _stats(fm, USER)


# ─── Session search (FTS5 over agent_messages) ─────────────────────────────


@router.post("/search", response_model=SessionSearchResponse)
def search_messages(
    req: SessionSearchRequest,
    store: ContentStore = Depends(get_store),
):
    results = store.search_agent_messages(req.q, limit=req.limit, thread_id=req.thread_id)
    return {"messages": results, "count": len(results)}


# ─── Snapshot management ───────────────────────────────────────────────────


@router.post("/refresh-snapshot")
def refresh_snapshot(req: RefreshSnapshotRequest):
    ChatAgentService.invalidate_frozen(req.thread_id)
    return {"refreshed": True, "thread_id": req.thread_id}
