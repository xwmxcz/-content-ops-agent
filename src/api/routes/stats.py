from fastapi import APIRouter, Depends

from src.api.dependencies import get_store
from src.storage import ContentStore


router = APIRouter()


@router.get("")
def get_stats(store: ContentStore = Depends(get_store)) -> dict:
    return store.get_content_stats()
