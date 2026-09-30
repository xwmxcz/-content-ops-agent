from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_store
from src.storage import ContentStore

router = APIRouter()


@router.get("")
def get_stats(store: ContentStore = Depends(get_store)) -> dict:
    return store.get_content_stats()


@router.get("/performance")
def get_performance_stats(
    days: int = Query(default=30, ge=1, le=365),
    platform: str | None = Query(default=None, max_length=50),
    store: ContentStore = Depends(get_store),
) -> dict:
    return store.get_performance_stats(days=days, platform=platform)
