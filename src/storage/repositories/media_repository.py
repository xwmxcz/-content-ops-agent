"""Media assets attached to content."""

import json
import logging
from typing import Any

from sqlalchemy import func

from src.storage.models import (
    MediaAsset,
)
from src.storage.repositories.base import RepositoryMixin

logger = logging.getLogger(__name__)


class MediaRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def save_media_asset(
        self,
        content_id: int,
        media_type: str,
        source_type: str,
        file_name: str,
        file_path: str,
        mime_type: str | None = None,
        provider: str | None = None,
        generation_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._get_session()
        try:
            current_order = (
                session.query(func.max(MediaAsset.sort_order))
                .filter(MediaAsset.content_id == content_id, MediaAsset.media_type == media_type)
                .scalar()
            )
            asset = MediaAsset(
                content_id=content_id,
                media_type=media_type,
                source_type=source_type,
                file_name=file_name,
                file_path=file_path,
                mime_type=mime_type,
                sort_order=(current_order or 0) + 1,
                provider=provider,
                generation_params=json.dumps(generation_params, ensure_ascii=False) if generation_params else None,
            )
            session.add(asset)
            session.flush()
            session.refresh(asset)
            # Finish metadata reads before commit so upload cleanup never
            # removes a file because a post-commit refresh or conversion failed.
            result = self._media_asset_to_dict(asset)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_media_asset(self, media_id: int) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            asset = session.query(MediaAsset).filter(MediaAsset.id == media_id).first()
            if not asset:
                return None
            return self._media_asset_to_dict(asset)
        finally:
            session.close()

    def list_media_assets(self, content_id: int, media_type: str | None = None) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(MediaAsset).filter(MediaAsset.content_id == content_id)
            if media_type:
                query = query.filter(MediaAsset.media_type == media_type)
            assets = query.order_by(MediaAsset.media_type, MediaAsset.sort_order, MediaAsset.created_at).all()
            return [self._media_asset_to_dict(asset) for asset in assets]
        finally:
            session.close()

    def delete_media_asset(self, media_id: int) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            asset = session.query(MediaAsset).filter(MediaAsset.id == media_id).first()
            if not asset:
                return None
            data = self._media_asset_to_dict(asset)
            session.delete(asset)
            session.commit()
            return data
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _media_asset_to_dict(asset: MediaAsset) -> dict[str, Any]:
        return {
            "id": asset.id,
            "content_id": asset.content_id,
            "media_type": asset.media_type,
            "source_type": asset.source_type,
            "file_name": asset.file_name,
            "file_path": asset.file_path,
            "mime_type": asset.mime_type,
            "sort_order": asset.sort_order or 0,
            "provider": asset.provider,
            "generation_params": json.loads(asset.generation_params) if asset.generation_params else None,
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        }
