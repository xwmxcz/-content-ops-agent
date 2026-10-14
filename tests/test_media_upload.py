import asyncio
from contextlib import contextmanager
from pathlib import Path
from tempfile import SpooledTemporaryFile
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_publish_service, get_store
from src.api.routes import media
from src.api.services.publish_service import PublishService
from src.storage import ContentStore
from src.storage.repositories.media_repository import MediaContentNotFound, MediaLimitExceeded
from src.utils import config


@pytest.fixture
def upload_store():
    store = Mock(spec=ContentStore)
    store.get_content.return_value = {"id": 1}
    store.list_media_assets.return_value = []
    store.save_media_asset.side_effect = lambda **kwargs: {"id": 7, **kwargs}
    return store


@pytest.fixture
def client(upload_store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "MEDIA_MAX_VIDEO_SIZE_MB", 1)
    app = FastAPI()
    app.include_router(media.router, prefix="/api")
    app.dependency_overrides[get_store] = lambda: upload_store
    app.dependency_overrides[get_publish_service] = lambda: PublishService(upload_store)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_image_upload_copies_in_bounded_chunks(client, monkeypatch):
    payload = b"image-data" * (256 * 1024)
    read_sizes = []
    original_read = SpooledTemporaryFile.read

    def tracked_read(file, size=-1):
        read_sizes.append(size)
        return original_read(file, size)

    monkeypatch.setattr(SpooledTemporaryFile, "read", tracked_read)
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("photo.PNG", payload, "image/png")},
    )

    assert response.status_code == 201
    asset = response.json()
    assert asset["file_name"] == "photo.PNG"
    assert asset["file_url"] == "/api/media/7/file"
    assert Path(asset["file_path"]).suffix == ".png"
    assert Path(asset["file_path"]).read_bytes() == payload
    assert read_sizes and all(0 < size <= 1024 * 1024 for size in read_sizes)


def test_failed_asset_save_removes_uploaded_file(client, upload_store, tmp_path):
    existing_file = tmp_path / "1" / "image" / "previous.png"
    existing_file.parent.mkdir(parents=True)
    existing_file.write_bytes(b"previous upload")
    upload_store.save_media_asset.side_effect = RuntimeError("database write failed")
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("photo.png", b"image-data", "image/png")},
    )

    assert response.status_code == 500
    upload_store.save_media_asset.assert_called_once()
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == [existing_file]
    assert existing_file.read_bytes() == b"previous upload"


def test_oversized_image_is_rejected_and_partial_file_is_removed(client, upload_store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_MAX_IMAGE_SIZE_MB", 1)
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("photo.png", b"x" * (1024 * 1024 + 1), "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Image file exceeds 1 MB"
    upload_store.save_media_asset.assert_not_called()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_image_exactly_at_the_limit_is_accepted(client, upload_store, monkeypatch):
    monkeypatch.setattr(config, "MEDIA_MAX_IMAGE_SIZE_MB", 1)
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("photo.png", b"x" * (1024 * 1024), "image/png")},
    )
    assert response.status_code == 201
    upload_store.save_media_asset.assert_called_once()


@pytest.mark.parametrize("error_type,http_status", [(MediaLimitExceeded, 400), (MediaContentNotFound, 404)])
def test_rejected_upload_cleans_up_only_its_new_file(client, upload_store, tmp_path, error_type, http_status):
    existing_file = tmp_path / "1" / "image" / "previous.png"
    existing_file.parent.mkdir(parents=True)
    existing_file.write_bytes(b"previous upload")
    upload_store.save_media_asset.side_effect = error_type("Upload rejected")

    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("photo.png", b"image-data", "image/png")},
    )

    assert response.status_code == http_status
    assert response.json()["detail"] == "Upload rejected"
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == [existing_file]
    assert existing_file.read_bytes() == b"previous upload"


def test_partial_write_failure_removes_file(client, upload_store, tmp_path, monkeypatch):
    original_open = Path.open

    @contextmanager
    def failing_open(path, *args, **kwargs):
        with original_open(path, *args, **kwargs) as destination:
            if path.parent == tmp_path / "1" / "image":

                def write_then_fail(chunk):
                    destination.write(chunk[:4])
                    raise OSError("disk full")

                writer = Mock(wraps=destination)
                writer.write.side_effect = write_then_fail
                yield writer
            else:
                yield destination

    monkeypatch.setattr(Path, "open", failing_open)
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("photo.png", b"image-data", "image/png")},
    )

    assert response.status_code == 500
    upload_store.save_media_asset.assert_not_called()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_upload_persistence_runs_outside_event_loop(client, upload_store):
    def save_in_worker(**kwargs):
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        return {"id": 7, **kwargs}

    upload_store.save_media_asset.side_effect = save_in_worker
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("photo.png", b"image-data", "image/png")},
    )

    assert response.status_code == 201
    upload_store.save_media_asset.assert_called_once()


@pytest.mark.parametrize(
    ("payload", "detail"),
    [(b"", "Uploaded file is empty"), (b"v" * (1024 * 1024 + 1), "Video file exceeds 1 MB")],
    ids=["empty", "oversized"],
)
def test_invalid_video_leaves_no_file(client, upload_store, tmp_path, payload, detail):
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "video"},
        files={"file": ("video.mp4", payload, "video/mp4")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == detail
    upload_store.save_media_asset.assert_not_called()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_video_at_size_limit_is_accepted(client):
    payload = b"v" * (1024 * 1024)
    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "video"},
        files={"file": ("video.mp4", payload, "video/mp4")},
    )

    assert response.status_code == 201
    assert Path(response.json()["file_path"]).read_bytes() == payload


def test_media_delete_succeeds_when_content_cleanup_removes_the_file_first(client, upload_store, tmp_path, monkeypatch):
    path = tmp_path / "1" / "image" / "old.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old")
    upload_store.delete_media_asset.return_value = {"id": 7, "file_path": str(path)}
    unlink = Path.unlink

    def concurrent_unlink(target, *args, **kwargs):
        # A content deletion races exactly with unlink, after any exists check.
        if target == path:
            unlink(target)
        return unlink(target, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", concurrent_unlink)

    response = client.delete("/api/media/7")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert not path.exists()


def test_content_directory_removed_during_upload_returns_not_found(client, upload_store, tmp_path, monkeypatch):
    open_file = Path.open
    upload_store.get_content.side_effect = [{"id": 1}, None]

    def missing_directory(target, *args, **kwargs):
        if target.parent == tmp_path / "1" / "image":
            raise FileNotFoundError("Content cleanup removed the directory")
        return open_file(target, *args, **kwargs)

    monkeypatch.setattr(Path, "open", missing_directory)

    response = client.post(
        "/api/media/upload",
        data={"content_id": 1, "media_type": "image"},
        files={"file": ("new.png", b"image-data", "image/png")},
    )

    assert response.status_code == 404
    upload_store.save_media_asset.assert_not_called()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
