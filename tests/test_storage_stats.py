from pathlib import Path

from src.models import ContentType, GeneratedContent
from src.storage import ContentStore


def test_content_stats_include_dynamic_statuses():
    db_path = Path("data/test_storage_stats.db")
    if db_path.exists():
        db_path.unlink()
    store = ContentStore(db_path=str(db_path))
    try:
        draft_id = store.save_content(
            GeneratedContent(
                title="Draft",
                content="Draft body",
                content_type=ContentType.XIAOHONGSHU,
            )
        )
        agent_id = store.save_content(
            GeneratedContent(
                title="Agent final",
                content="Agent body",
                content_type=ContentType.BLOG,
            )
        )
        store.update_content(agent_id, status="agent_final")

        stats = store.get_content_stats()

        assert stats["total_contents"] == 2
        assert stats["by_type"] == {"blog": 1, "xiaohongshu": 1}
        assert stats["by_status"] == {"agent_final": 1, "draft": 1}
        assert store.get_content(draft_id)["status"] == "draft"
    finally:
        store.engine.dispose()
        if db_path.exists():
            db_path.unlink()
