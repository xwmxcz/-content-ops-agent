from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.integrations.mcp_client import XiaohongshuMcpClient
from src.storage import ContentStore
from src.utils import config, metrics
from src.utils.idempotency import (
    SCOPE_PUBLICATION_EXECUTE,
    idempotent_write_async,
    publication_request_id,
)
from src.utils.structured_logging import log_event

logger = logging.getLogger(__name__)


class PublicationValidationError(ValueError):
    """Raised when a publication request is invalid."""


class PublishService:
    XIAOHONGSHU_TITLE_MAX_LENGTH = 20

    def __init__(self, store: ContentStore, mcp_client: XiaohongshuMcpClient | None = None) -> None:
        self.store = store
        self.mcp_client = mcp_client or XiaohongshuMcpClient()

    async def get_login_status(self) -> dict[str, Any]:
        result = await self.mcp_client.check_login_status()
        status_text = result.get("text") or ""
        data = result.get("data")
        connected = None
        if isinstance(data, dict):
            for key in ("is_logged_in", "logged_in"):
                if isinstance(data.get(key), bool):
                    connected = data[key]
                    break
        if connected is None:
            # MCP text responses and REST boolean responses are both supported.
            # Unknown/empty output cannot establish that the account is logged in.
            negative = re.search(r"not\s+logged\s*in|logged\s*out|未登录|未登陆|登录失效|登录过期", status_text, re.I)
            positive = re.search(r"\blogged\s+in\b|\blogin\s+successful\b|已登录|已登陆|登录成功", status_text, re.I)
            connected = bool(positive and not negative)
        return {
            "connected": connected,
            "status_text": status_text,
            "details": data or result.get("raw"),
        }

    def create_publication_request(
        self,
        content_id: int,
        publish_type: str,
        title: str | None = None,
        body: str | None = None,
        media_ids: list[int] | None = None,
        scheduled_at: datetime | None = None,
        tags: list[str] | None = None,
        visibility: str = "public",
        is_original: bool = False,
        status: str = "queued",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        content = self.store.get_content(content_id)
        if not content:
            raise LookupError(f"Content {content_id} was not found")

        media_assets = self._select_media_assets(content_id, publish_type, media_ids)
        resolved_title = self._normalize_title(title or content.get("title") or content["content"][:30])
        resolved_body = (content["content"] if body is None else body).strip()
        if not resolved_body:
            raise PublicationValidationError("Publication content must not be empty")
        resolved_tags = (content.get("tags") or []) if tags is None else tags

        request_payload = {
            "title": resolved_title,
            "content": resolved_body,
            "tags": resolved_tags,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "visibility": visibility,
            "is_original": is_original,
            "media_ids": [asset["id"] for asset in media_assets],
        }
        if idempotency_key is not None:
            request_payload["_http_idempotency_key"] = idempotency_key
        if publish_type == "image_post":
            request_payload["images"] = [asset["file_path"] for asset in media_assets]
        else:
            request_payload["video"] = media_assets[0]["file_path"]

        return self.store.create_publication(
            content_id=content_id,
            platform="xiaohongshu",
            publish_type=publish_type,
            status=status,
            title=resolved_title,
            body=resolved_body,
            scheduled_at=scheduled_at,
            request_payload=request_payload,
        )

    async def execute_publication(self, publication_id: int) -> dict[str, Any]:
        publication = self.store.get_publication(publication_id)
        if not publication:
            raise LookupError(f"Publication {publication_id} was not found")

        # Legacy publications may have completed without an execution ledger.
        # Their terminal state still proves that the platform accepted the post.
        if publication["status"] in {"completed", "scheduled"}:
            return publication

        # The key is the publication row, not the job attempt: a requeued job, a
        # worker restart, and a manual retry are all the same logical publication,
        # and publishing twice to a real platform is not reversible.
        # An absent HTTP key permits a new publication row for each POST; it
        # never permits executing the same row more than once.
        return await idempotent_write_async(
            self.store,
            scope=SCOPE_PUBLICATION_EXECUTE,
            key=publication_request_id(publication_id),
            args={"publication_id": int(publication_id)},
            external_request_id=publication_request_id(publication_id),
            write=lambda: self._execute_publication_once(publication_id, publication),
        )

    async def _execute_publication_once(
        self,
        publication_id: int,
        publication: dict[str, Any],
    ) -> dict[str, Any]:
        request_payload = publication.get("request_payload") or {}
        self.store.update_publication(publication_id, status="running", error_message=None)

        # P2-01: Track publication request and duration
        start_time = time.time()
        platform = publication.get("platform", "xiaohongshu")
        metrics.publication_requests_total.labels(platform=platform, status="pending").inc()

        try:
            tool_response = await self._call_publish_tool(
                publication["publish_type"],
                request_payload,
                external_request_id=publication_request_id(publication_id),
            )
            response_data = tool_response.get("data")
            response_payload = (
                response_data if isinstance(response_data, dict) else {"text": tool_response.get("text", "")}
            )
            final_status = "scheduled" if request_payload.get("scheduled_at") else "completed"
            published_at = None if final_status == "scheduled" else datetime.now()
            external_post_id = self._extract_external_post_id(response_payload, tool_response.get("text", ""))

            updated = self.store.update_publication(
                publication_id,
                status=final_status,
                published_at=published_at,
                external_post_id=external_post_id,
                response_payload=response_payload,
                error_message=None,
            )
            if final_status == "completed":
                self.store.update_content(publication["content_id"], status="published")
            elif final_status == "scheduled":
                self.store.update_content(publication["content_id"], status="scheduled")
                scheduled_date = datetime.fromisoformat(request_payload["scheduled_at"]).date()
                self.store.save_calendar_event(
                    publication["content_id"], "xiaohongshu", scheduled_date, status="scheduled"
                )

            # P2-01: Track success
            duration = time.time() - start_time
            metrics.publication_requests_total.labels(platform=platform, status=final_status).inc()
            metrics.publication_duration_seconds.labels(platform=platform).observe(duration)
            log_event(
                logger,
                "publication_completed",
                level=logging.INFO,
                publication_id=publication_id,
                platform=platform,
                status=final_status,
                duration_seconds=duration,
            )

            return updated or publication
        except Exception as exc:
            self.store.update_publication(publication_id, status="failed", error_message=str(exc))

            # P2-01: Track failure
            duration = time.time() - start_time
            metrics.publication_requests_total.labels(platform=platform, status="failed").inc()
            metrics.publication_duration_seconds.labels(platform=platform).observe(duration)
            log_event(
                logger,
                "publication_failed",
                level=logging.ERROR,
                publication_id=publication_id,
                platform=platform,
                error=str(exc),
                duration_seconds=duration,
            )
            raise

    def _select_media_assets(
        self, content_id: int, publish_type: str, media_ids: list[int] | None
    ) -> list[dict[str, Any]]:
        if publish_type not in {"image_post", "video_post"}:
            raise PublicationValidationError(f"Unsupported publish type: {publish_type}")
        expected_type = "image" if publish_type == "image_post" else "video"
        assets = self.store.list_media_assets(content_id, media_type=expected_type)
        if media_ids is not None:
            if len(set(media_ids)) != len(media_ids):
                raise PublicationValidationError("Media selection must not contain duplicate IDs")
            available = {asset["id"]: asset for asset in assets}
            if any(media_id not in available for media_id in media_ids):
                raise PublicationValidationError(
                    "Selected media must belong to this content and match the publish type"
                )
            # The first image is the cover; preserve the caller's chosen order.
            assets = [available[media_id] for media_id in media_ids]
        if publish_type == "image_post":
            if not assets:
                raise PublicationValidationError("Image posts require at least one uploaded image")
            if len(assets) > config.MEDIA_MAX_IMAGE_COUNT:
                raise PublicationValidationError(f"Image posts support at most {config.MEDIA_MAX_IMAGE_COUNT} images")
            return assets
        if len(assets) != 1:
            raise PublicationValidationError("Video posts require exactly one uploaded video")
        return assets

    async def _call_publish_tool(
        self,
        publish_type: str,
        request_payload: dict[str, Any],
        *,
        external_request_id: str | None = None,
    ) -> dict[str, Any]:
        tool_args = {
            "title": request_payload["title"],
            "content": request_payload["content"],
            "tags": request_payload.get("tags") or [],
            "schedule_at": request_payload.get("scheduled_at"),
            "visibility": request_payload.get("visibility", "public"),
            "is_original": request_payload.get("is_original", False),
        }
        if external_request_id:
            # Sent so the platform can reject a duplicate it has already accepted.
            # Whether it honors the token is the provider's contract, not ours:
            # this side guarantees the token is stable across retries, nothing more.
            tool_args["request_id"] = external_request_id
        if publish_type == "image_post":
            tool_args["images"] = request_payload["images"]
            return await self.mcp_client.publish_content(tool_args)
        tool_args["video"] = request_payload["video"]
        return await self.mcp_client.publish_with_video(tool_args)

    @staticmethod
    def validate_upload(media_type: str, filename: str, mime_type: str | None) -> None:
        suffix = Path(filename).suffix.lower()
        if media_type == "image":
            if mime_type and not mime_type.startswith("image/"):
                raise PublicationValidationError("Only image files can be uploaded as image assets")
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise PublicationValidationError("Unsupported image file type")
            return
        if media_type == "video":
            if mime_type and not mime_type.startswith("video/"):
                raise PublicationValidationError("Only video files can be uploaded as video assets")
            if suffix not in {".mp4", ".mov", ".m4v"}:
                raise PublicationValidationError("Unsupported video file type")
            return
        raise PublicationValidationError(f"Unsupported media type: {media_type}")

    @staticmethod
    def _extract_external_post_id(payload: dict[str, Any], fallback_text: str) -> str | None:
        for key in ("post_id", "note_id", "feed_id", "id"):
            value = payload.get(key)
            if value:
                return str(value)
        return fallback_text[:120] or None

    @classmethod
    def _normalize_title(cls, raw_title: str) -> str:
        title = raw_title.strip()
        title = re.sub(r"^[#\s]+", "", title)
        title = title.splitlines()[0].strip() if title else ""
        title = re.sub(r"\s+", " ", title)
        return title[: cls.XIAOHONGSHU_TITLE_MAX_LENGTH] or "Post"


def create_publish_service(store: ContentStore) -> PublishService:
    return PublishService(store=store)
