"""Publish intent and retry regressions, with no external platform or database."""

from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.api.routes import publish as publish_routes
from src.api.schemas.publish import XiaohongshuPublishRequest
from src.api.services.publish_service import PublicationValidationError, PublishService
from src.jobs.queue import JobCapacityError, JobQueueError
from src.utils.idempotency import DuplicateRequestInFlight, IdempotencyKeyConflict


class PublicationStore:
    """In-memory persistence for exercising the real route/service/ledger flow."""

    def __init__(self):
        self.publications = {}
        self.records = {}
        self.events = []
        self.content = {"id": 1, "title": "Draft title", "content": "Draft body", "tags": ["old"]}
        self.assets = [
            {"id": 1, "media_type": "image", "file_path": "first.jpg"},
            {"id": 2, "media_type": "image", "file_path": "second.jpg"},
            {"id": 3, "media_type": "video", "file_path": "video.mp4"},
        ]

    def get_content(self, content_id):
        return deepcopy(self.content) if content_id == 1 else None

    def list_media_assets(self, content_id, media_type):
        return [deepcopy(asset) for asset in self.assets if asset["media_type"] == media_type]

    def create_publication(self, **fields):
        publication_id = len(self.publications) + 1
        self.publications[publication_id] = {"id": publication_id, **deepcopy(fields)}
        return self.get_publication(publication_id)

    def get_publication(self, publication_id):
        return deepcopy(self.publications.get(publication_id))

    def update_publication(self, publication_id, **fields):
        self.publications[publication_id].update(deepcopy(fields))
        return self.get_publication(publication_id)

    def update_content(self, content_id, **fields):
        self.content.update(fields)

    def save_calendar_event(self, content_id, platform, scheduled_date, *, status="planned"):
        self.events.append((content_id, platform, scheduled_date, status))

    def claim_idempotency_key(self, *, scope, key, args, external_request_id):
        identity = (scope, key)
        record = self.records.get(identity)
        if record:
            if record["args"] != args:
                raise IdempotencyKeyConflict("Idempotency key reused with different arguments")
            if record["status"] == "completed":
                return {"outcome": "replay", "result": deepcopy(record["result"])}
            if record["status"] == "in_progress":
                raise DuplicateRequestInFlight("Publication already executing")
        self.records[identity] = {"args": deepcopy(args), "status": "in_progress"}
        return {"outcome": "claimed", "record_id": identity}

    def complete_idempotency_key(self, record_id, *, result):
        self.records[record_id].update(status="completed", result=deepcopy(result))

    def fail_idempotency_key(self, record_id):
        self.records[record_id]["status"] = "failed"


@pytest.fixture
def publication_setup(monkeypatch):
    store = PublicationStore()
    mcp = AsyncMock()
    mcp.publish_content.return_value = {"data": {"post_id": "published-1"}}
    service = PublishService(store, mcp_client=mcp)
    jobs = []

    def enqueue(job_type, payload, current_store, background_tasks):
        jobs.append(payload)
        return {"id": f"job_{len(jobs)}"}

    monkeypatch.setattr(publish_routes, "create_and_enqueue_job", enqueue)
    return store, service, mcp, jobs


def _enqueue(service, store, payload=None, key=None):
    request = XiaohongshuPublishRequest.model_validate(
        {"content_id": 1, "publish_type": "image_post", **(payload or {})}
    )
    return publish_routes._enqueue_publication(
        request, BackgroundTasks(), service, store, require_future=False, idempotency_key=key
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,connected",
    [
        ({"data": {"is_logged_in": False}, "text": "Request successful"}, False),
        ({"data": {"is_logged_in": True}, "text": ""}, True),
        ({"data": {"logged_in": False}, "text": "Logged in"}, False),
        ({"data": {"logged_in": True}}, True),
        ({"text": "✅ 已登录"}, True),
        ({"text": "❌ 未登录，请扫码登录"}, False),
        ({"text": "Logged in"}, True),
        ({"text": "Not logged in"}, False),
        ({"text": ""}, False),
    ],
)
async def test_login_status_uses_the_providers_actual_verdict(publication_setup, response, connected):
    _, service, mcp, _ = publication_setup
    mcp.check_login_status.return_value = response

    assert (await service.get_login_status())["connected"] is connected


@pytest.mark.parametrize(
    "changed",
    [
        {"title": "Changed title"},
        {"content": "Changed body"},
        {"media_ids": [2, 1]},
        {"tags": []},
        {"visibility": "self-only"},
        {"is_original": True},
    ],
)
def test_reusing_a_publish_key_cannot_discard_changed_intent(publication_setup, changed):
    store, service, _, jobs = publication_setup
    first = _enqueue(service, store, key="request-1")

    with pytest.raises(HTTPException) as error:
        _enqueue(service, store, payload=changed, key="request-1")

    assert error.value.status_code == 422
    assert len(store.publications) == len(jobs) == 1
    assert _enqueue(service, store, key="request-1") == first


def test_selected_media_preserves_cover_order_and_empty_tags(publication_setup):
    store, service, _, _ = publication_setup

    publication = service.create_publication_request(1, "image_post", media_ids=[2, 1], tags=[])

    assert publication["request_payload"]["images"] == ["second.jpg", "first.jpg"]
    assert publication["request_payload"]["media_ids"] == [2, 1]
    assert publication["request_payload"]["tags"] == []


@pytest.mark.parametrize("media_ids", [[], [1, 999], [1, 3], [1, 1]])
def test_invalid_media_selection_never_silently_changes_the_post(publication_setup, media_ids):
    store, service, _, _ = publication_setup

    with pytest.raises(PublicationValidationError):
        service.create_publication_request(1, "image_post", media_ids=media_ids)

    assert store.publications == {}


@pytest.mark.parametrize("body", ["", " \n "])
def test_empty_edited_body_is_rejected_instead_of_publishing_the_old_body(publication_setup, body):
    store, service, _, _ = publication_setup

    with pytest.raises(PublicationValidationError, match="must not be empty"):
        service.create_publication_request(1, "image_post", body=body)

    assert store.publications == {}


def test_blank_title_does_not_crash_before_publication_validation(publication_setup):
    _, service, _, _ = publication_setup
    assert service.create_publication_request(1, "image_post", title=" # \n ")["title"] == "Post"


@pytest.mark.asyncio
async def test_http_posts_without_a_key_are_distinct_but_each_job_executes_once(publication_setup):
    store, service, mcp, jobs = publication_setup
    first = _enqueue(service, store)["publication"]
    second = _enqueue(service, store)["publication"]

    for publication in (first, second):
        await service.execute_publication(publication["id"])
        await service.execute_publication(publication["id"])

    assert first["id"] != second["id"]
    assert len(jobs) == mcp.publish_content.await_count == 2


@pytest.mark.asyncio
async def test_in_progress_retry_without_http_key_does_not_reach_platform(publication_setup):
    store, service, mcp, _ = publication_setup
    publication = _enqueue(service, store)["publication"]
    nested_attempts = []

    async def publish(arguments):
        with pytest.raises(DuplicateRequestInFlight):
            await service.execute_publication(publication["id"])
        nested_attempts.append(True)
        return {"data": {"post_id": "published-1"}}

    mcp.publish_content.side_effect = publish
    await service.execute_publication(publication["id"])

    assert nested_attempts == [True]
    assert mcp.publish_content.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "scheduled"])
async def test_legacy_finished_publications_never_publish_again(publication_setup, status):
    store, service, mcp, _ = publication_setup
    publication = service.create_publication_request(1, "image_post")
    store.update_publication(publication["id"], status=status, request_payload={"_skip_execute_idempotency": True})

    assert (await service.execute_publication(publication["id"]))["status"] == status
    mcp.publish_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_job_retry_creates_only_one_calendar_event(publication_setup):
    store, service, mcp, _ = publication_setup
    publication = _enqueue(service, store, payload={"scheduled_at": (datetime.now() + timedelta(days=1)).isoformat()})[
        "publication"
    ]

    await service.execute_publication(publication["id"])
    await service.execute_publication(publication["id"])

    assert len(store.events) == mcp.publish_content.await_count == 1
    assert store.events[0][3] == "scheduled"


@pytest.mark.parametrize("require_future", [False, True])
def test_past_schedule_is_rejected_on_both_publish_routes(publication_setup, require_future):
    store, service, mcp, jobs = publication_setup
    request = XiaohongshuPublishRequest(
        content_id=1, publish_type="image_post", scheduled_at=datetime.now() - timedelta(minutes=1)
    )
    with pytest.raises(HTTPException) as error:
        publish_routes._enqueue_publication(request, BackgroundTasks(), service, store, require_future=require_future)
    assert error.value.status_code == 400
    assert jobs == []
    assert store.publications == {}
    mcp.publish_content.assert_not_awaited()


@pytest.mark.parametrize("error_type,http_status", [(JobCapacityError, 429), (JobQueueError, 503)])
def test_queue_rejection_marks_publication_failed(publication_setup, monkeypatch, error_type, http_status):
    store, service, _, _ = publication_setup

    def reject(*args):
        raise error_type("Queue unavailable")

    monkeypatch.setattr(publish_routes, "create_and_enqueue_job", reject)

    with pytest.raises(HTTPException) as error:
        _enqueue(service, store)

    assert error.value.status_code == http_status
    assert store.publications[1]["status"] == "failed"
    assert store.publications[1]["error_message"] == "Queue unavailable"
