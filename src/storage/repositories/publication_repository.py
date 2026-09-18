"""Publication requests sent to external platforms."""

import json
import logging
from datetime import datetime
from typing import Any

from src.storage.models import (
    PlatformPublication,
)
from src.storage.repositories.base import RepositoryMixin

logger = logging.getLogger(__name__)


class PublicationRepositoryMixin(RepositoryMixin):
    """See :class:`src.storage.content_store.ContentStore` for the shared contract.

    Mixed into ``ContentStore``; ``session``/``_get_session`` come from the host
    class, which is why this is a mixin rather than a standalone object.
    """

    def create_publication(
        self,
        content_id: int,
        platform: str,
        publish_type: str,
        status: str,
        title: str | None,
        body: str,
        scheduled_at: datetime | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._get_session()
        try:
            publication = PlatformPublication(
                content_id=content_id,
                platform=platform,
                publish_type=publish_type,
                status=status,
                title=title,
                body=body,
                scheduled_at=scheduled_at,
                request_payload=json.dumps(request_payload, ensure_ascii=False) if request_payload else None,
            )
            session.add(publication)
            session.commit()
            session.refresh(publication)
            return self._publication_to_dict(publication)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_publication(self, publication_id: int) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            publication = session.query(PlatformPublication).filter(PlatformPublication.id == publication_id).first()
            if not publication:
                return None
            return self._publication_to_dict(publication)
        finally:
            session.close()

    def list_publications(self, content_id: int) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            publications = (
                session.query(PlatformPublication)
                .filter(PlatformPublication.content_id == content_id)
                .order_by(PlatformPublication.created_at.desc())
                .all()
            )
            return [self._publication_to_dict(publication) for publication in publications]
        finally:
            session.close()

    def update_publication(self, publication_id: int, **fields) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            publication = session.query(PlatformPublication).filter(PlatformPublication.id == publication_id).first()
            if not publication:
                return None

            for key in ("request_payload", "response_payload"):
                if key in fields and fields[key] is not None:
                    fields[key] = json.dumps(fields[key], ensure_ascii=False)

            for key, value in fields.items():
                if hasattr(publication, key):
                    setattr(publication, key, value)
            publication.updated_at = datetime.now()
            session.commit()
            session.refresh(publication)
            return self._publication_to_dict(publication)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _publication_to_dict(publication: PlatformPublication) -> dict[str, Any]:
        return {
            "id": publication.id,
            "content_id": publication.content_id,
            "platform": publication.platform,
            "publish_type": publication.publish_type,
            "status": publication.status,
            "title": publication.title,
            "body": publication.body,
            "scheduled_at": publication.scheduled_at.isoformat() if publication.scheduled_at else None,
            "published_at": publication.published_at.isoformat() if publication.published_at else None,
            "external_post_id": publication.external_post_id,
            "request_payload": json.loads(publication.request_payload) if publication.request_payload else None,
            "response_payload": json.loads(publication.response_payload) if publication.response_payload else None,
            "error_message": publication.error_message,
            "created_at": publication.created_at.isoformat() if publication.created_at else None,
            "updated_at": publication.updated_at.isoformat() if publication.updated_at else None,
        }
