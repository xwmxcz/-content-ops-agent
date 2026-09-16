"""Media metadata must be ready before commit so failed uploads can remove their file."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from src.models import ContentType, GeneratedContent
from src.storage import ContentStore


@pytest.fixture
def media_fields(tmp_path):
    return {
        "content_id": 1,
        "media_type": "image",
        "source_type": "generated",
        "file_name": "image.png",
        "file_path": str(tmp_path / "image.png"),
        "mime_type": "image/png",
        "provider": "test-provider",
        "generation_params": {"prompt": "media test"},
    }


@pytest.fixture
def mocked_store(monkeypatch):
    store = ContentStore.__new__(ContentStore)
    session = Mock(spec=Session)
    session.query.return_value.filter.return_value.scalar.return_value = 2
    monkeypatch.setattr(store, "_get_session", lambda: session)

    def refresh(asset):
        asset.id = 7
        asset.created_at = datetime(2026, 1, 1)

    session.refresh.side_effect = refresh
    serializer = Mock(wraps=store._media_asset_to_dict)
    monkeypatch.setattr(store, "_media_asset_to_dict", serializer)
    operations = Mock()
    operations.attach_mock(session, "session")
    operations.attach_mock(serializer, "serialize")
    return store, session, serializer, operations


def test_save_media_asset_prepares_metadata_before_commit(mocked_store, media_fields):
    store, session, serializer, operations = mocked_store

    result = store.save_media_asset(**media_fields)

    assert result == {
        "id": 7,
        **media_fields,
        "sort_order": 3,
        "created_at": "2026-01-01T00:00:00",
    }
    assert [call[0] for call in operations.mock_calls if not call[0].startswith("session.query")] == [
        "session.add",
        "session.flush",
        "session.refresh",
        "serialize",
        "session.commit",
        "session.close",
    ]
    asset = session.add.call_args.args[0]
    session.refresh.assert_called_once_with(asset)
    serializer.assert_called_once_with(asset)
    session.rollback.assert_not_called()


@pytest.mark.parametrize("failure_stage", ["refresh", "serialize"])
def test_media_metadata_failure_rolls_back_without_commit(mocked_store, media_fields, failure_stage):
    store, session, serializer, _ = mocked_store
    operation = session.refresh if failure_stage == "refresh" else serializer
    operation.side_effect = RuntimeError("metadata failed")

    with pytest.raises(RuntimeError, match="metadata failed"):
        store.save_media_asset(**media_fields)

    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_saved_media_metadata_matches_persisted_row(store, media_fields):
    media_fields["content_id"] = store.save_content(
        GeneratedContent(content="media test", content_type=ContentType.XIAOHONGSHU)
    )

    result = store.save_media_asset(**media_fields)

    assert result["id"] > 0
    assert result["created_at"]
    assert result["sort_order"] == 1
    assert all(result[key] == value for key, value in media_fields.items())
    assert store.get_media_asset(result["id"]) == result


@pytest.mark.parametrize("failure_stage", ["refresh", "serialize"])
def test_media_metadata_failure_does_not_persist_row(store, media_fields, monkeypatch, failure_stage):
    media_fields["content_id"] = store.save_content(
        GeneratedContent(content="media test", content_type=ContentType.XIAOHONGSHU)
    )
    session = store._get_session()
    with monkeypatch.context() as patch:
        patch.setattr(store, "_get_session", lambda: session)
        target = session if failure_stage == "refresh" else store
        method = "refresh" if failure_stage == "refresh" else "_media_asset_to_dict"
        patch.setattr(target, method, Mock(side_effect=RuntimeError("metadata failed")))

        with pytest.raises(RuntimeError, match="metadata failed"):
            store.save_media_asset(**media_fields)

    assert store.list_media_assets(media_fields["content_id"]) == []
