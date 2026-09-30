"""Real PostgreSQL regressions for media capacity and concurrent deletion."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_publish_service, get_store, get_system_store
from src.api.routes import content as content_routes
from src.api.routes import media as media_routes
from src.api.services.publish_service import PublishService
from src.models import ContentType, GeneratedContent
from src.storage.models import Content, MediaAsset, User
from src.storage.repositories.media_repository import MediaContentNotFound, MediaLimitExceeded
from src.utils import config


@pytest.fixture
def media_client(store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_STORAGE_ROOT", str(tmp_path / "media"))
    monkeypatch.setattr(config, "MEDIA_MAX_IMAGE_COUNT", 3)
    app = FastAPI()
    app.include_router(media_routes.router, prefix="/api")
    app.include_router(content_routes.router, prefix="/api/content")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_publish_service] = lambda: PublishService(store)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _content(store):
    return store.save_content(GeneratedContent(title="Media", content="Body", content_type=ContentType.XIAOHONGSHU))


def _seed_asset(store, content_id, index=0, media_type="image", source_type="upload"):
    suffix = ".png" if media_type == "image" else ".mp4"
    path = Path(config.MEDIA_STORAGE_ROOT) / str(content_id) / media_type / f"existing-{index}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(f"original-{index}".encode())
    return store.save_media_asset(content_id, media_type, source_type, path.name, str(path))


def _upload(client, content_id, media_type="image", index=0):
    extension, mime = ("png", "image/png") if media_type == "image" else ("mp4", "video/mp4")
    return client.post(
        "/api/media/upload",
        data={"content_id": content_id, "media_type": media_type},
        files={"file": (f"new-{index}.{extension}", f"new-{index}".encode(), mime)},
    )


@pytest.mark.parametrize("media_type,existing_count,capacity", [("image", 2, 3), ("video", 0, 1)])
def test_concurrent_uploads_never_overfill_content_or_leave_rejected_files(
    store, media_client, monkeypatch, media_type, existing_count, capacity
):
    content_id = _content(store)
    existing = [_seed_asset(store, content_id, index, media_type) for index in range(existing_count)]
    start = threading.Barrier(6)
    save_asset = store.save_media_asset
    open_session = store._get_session

    def synchronized_save(**kwargs):
        # All requests have passed route validation and written their own file.
        start.wait(timeout=10)
        return save_asset(**kwargs)

    def slow_insert_session():
        session = open_session()
        add = session.add

        def delayed_add(instance, *args, **kwargs):
            if isinstance(instance, MediaAsset):
                # Expose check-then-insert races even if an implementation adds
                # the capacity check but forgets to serialize it with the write.
                time.sleep(0.2)
            return add(instance, *args, **kwargs)

        session.add = delayed_add
        return session

    monkeypatch.setattr(store, "save_media_asset", synchronized_save)
    monkeypatch.setattr(store, "_get_session", slow_insert_session)
    with ThreadPoolExecutor(max_workers=6) as workers:
        futures = [workers.submit(_upload, media_client, content_id, media_type, index) for index in range(6)]
        responses = [future.result(timeout=20) for future in futures]

    assert sorted(response.status_code for response in responses) == [201, 400, 400, 400, 400, 400]
    assets = store.list_media_assets(content_id, media_type=media_type)
    assert len(assets) == capacity
    assert [asset["sort_order"] for asset in assets] == list(range(1, capacity + 1))
    files = {path for path in Path(config.MEDIA_STORAGE_ROOT).rglob("*") if path.is_file()}
    assert files == {Path(asset["file_path"]) for asset in assets}
    for index, asset in enumerate(existing):
        assert Path(asset["file_path"]).read_bytes() == f"original-{index}".encode()


def test_storage_callers_share_capacity_and_deleting_media_frees_a_slot(store, media_client):
    content_id = _content(store)
    existing = [_seed_asset(store, content_id, index, source_type="generated") for index in range(3)]

    with pytest.raises(MediaLimitExceeded):
        store.save_media_asset(content_id, "image", "generated", "new.png", "new.png")
    assert len(store.list_media_assets(content_id)) == 3
    assert media_client.delete(f"/api/media/{existing[1]['id']}").status_code == 200

    uploaded = _upload(media_client, content_id)
    assert uploaded.status_code == 201
    assert uploaded.json()["sort_order"] == 4
    assert len(store.list_media_assets(content_id)) == 3


def test_media_creation_for_missing_or_foreign_content_is_an_access_miss(store, media_client):
    system = get_system_store()
    foreign_user = "99999999999999999999999999999999"
    with system._get_session() as session:
        session.add(User(id=foreign_user, username="media_other", password_hash="!", is_active=True))
        session.commit()
    foreign_id = _content(system.for_user(foreign_user))

    for content_id in (foreign_id, 999999):
        with pytest.raises(MediaContentNotFound):
            store.save_media_asset(content_id, "image", "upload", "new.png", "new.png")
        assert _upload(media_client, content_id).status_code == 404
    assert system.for_user(foreign_user).list_media_assets(foreign_id) == []
    assert not Path(config.MEDIA_STORAGE_ROOT).exists()


def test_content_deleted_during_upload_returns_404_and_removes_new_file(store, media_client, monkeypatch):
    content_id = _content(store)
    saving = threading.Event()
    save_asset = store.save_media_asset

    def observe_save(**kwargs):
        saving.set()
        return save_asset(**kwargs)

    monkeypatch.setattr(store, "save_media_asset", observe_save)
    # The HTTP precheck can still see the committed row while deletion holds
    # the lock. Persistence must recheck existence after that lock is released.
    with store._get_session() as deletion:
        content = deletion.query(Content).filter(Content.id == content_id).with_for_update().one()
        deletion.delete(content)
        deletion.flush()
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(_upload, media_client, content_id)
            try:
                assert saving.wait(timeout=10)
            finally:
                deletion.commit()
            response = future.result(timeout=10)

    assert response.status_code == 404
    assert store.list_media_assets(content_id) == []
    assert not [path for path in Path(config.MEDIA_STORAGE_ROOT).rglob("*") if path.is_file()]


def test_upload_waits_for_media_deletion_and_uses_the_freed_capacity(store, media_client, monkeypatch):
    content_id = _content(store)
    existing = _seed_asset(store, content_id, media_type="video")
    saving = threading.Event()
    save_asset = store.save_media_asset

    def observe_save(**kwargs):
        saving.set()
        return save_asset(**kwargs)

    monkeypatch.setattr(store, "save_media_asset", observe_save)
    with store._get_session() as deletion:
        deletion.query(Content.id).filter(Content.id == content_id).with_for_update().one()
        asset = deletion.query(MediaAsset).filter(MediaAsset.id == existing["id"]).one()
        deletion.delete(asset)
        deletion.flush()
        with ThreadPoolExecutor(max_workers=1) as workers:
            future = workers.submit(_upload, media_client, content_id, "video")
            try:
                assert saving.wait(timeout=10)
            finally:
                deletion.commit()
            response = future.result(timeout=10)

    assert response.status_code == 201
    assert [asset["id"] for asset in store.list_media_assets(content_id)] == [response.json()["id"]]


def test_content_deletion_waits_for_in_progress_upload_and_removes_its_asset(store, media_client, monkeypatch):
    content_id = _content(store)
    inserting = threading.Event()
    deleting = threading.Event()
    release_upload = threading.Event()
    open_session = store._get_session
    delete_content = store.delete_content

    def observe_delete(content_id):
        deleting.set()
        return delete_content(content_id)

    def paused_insert_session():
        session = open_session()
        add = session.add

        def paused_add(instance, *args, **kwargs):
            if isinstance(instance, MediaAsset):
                inserting.set()
                assert release_upload.wait(timeout=10)
            return add(instance, *args, **kwargs)

        session.add = paused_add
        return session

    monkeypatch.setattr(store, "_get_session", paused_insert_session)
    monkeypatch.setattr(store, "delete_content", observe_delete)
    with ThreadPoolExecutor(max_workers=2) as workers:
        upload = workers.submit(_upload, media_client, content_id)
        try:
            assert inserting.wait(timeout=10)
            deletion = workers.submit(media_client.delete, f"/api/content/{content_id}")
            assert deleting.wait(timeout=10)
        finally:
            release_upload.set()
        assert upload.result(timeout=10).status_code == 201
        assert deletion.result(timeout=10).status_code == 200

    assert store.get_content(content_id) is None
    assert store.list_media_assets(content_id) == []
    assert not [path for path in Path(config.MEDIA_STORAGE_ROOT).rglob("*") if path.is_file()]
