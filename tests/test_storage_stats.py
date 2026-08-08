from datetime import date, datetime, timedelta

from src.models import ContentType, GeneratedContent
from src.storage.content_store import ContentMetrics


def test_content_stats_include_dynamic_statuses(store):
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


def test_aggregate_performance_returns_grouped_stats(store):
    # 3 xhs (2 with metrics, one a clear winner) + 1 blog (with metrics)
    ids = []
    for title in ("xhs A", "xhs B", "xhs C"):
        ids.append(store.save_content(GeneratedContent(
            title=title, content="body", content_type=ContentType.XIAOHONGSHU,
        ), style="professional"))
    ids.append(store.save_content(GeneratedContent(
        title="blog A", content="body", content_type=ContentType.BLOG,
    ), style="storytelling"))

    session = store._get_session()
    try:
        session.add_all([
            ContentMetrics(content_id=ids[0], platform="xiaohongshu",
                           views=1000, likes=100, comments=10, shares=5),
            ContentMetrics(content_id=ids[1], platform="xiaohongshu",
                           views=20000, likes=2000, comments=200, shares=200),  # winner
            ContentMetrics(content_id=ids[3], platform="blog",
                           views=5000, likes=300, comments=30, shares=15),
        ])
        session.commit()
    finally:
        session.close()

    perf = store.aggregate_performance(days=30)
    assert perf["total_contents"] == 4
    assert perf["total_with_metrics"] == 3

    type_index = {row["content_type"]: row for row in perf["by_type"]}
    assert type_index["xiaohongshu"]["count"] == 3
    assert type_index["xiaohongshu"]["with_metrics"] == 2
    assert type_index["blog"]["count"] == 1
    assert type_index["xiaohongshu"]["avg_engagement_rate"] > 0

    # Top performer is the xhs B winner.
    assert perf["top_performers"][0]["id"] == ids[1]
    assert perf["top_performers"][0]["views"] == 20000


def test_aggregate_performance_handles_empty_window(store):
    perf = store.aggregate_performance(days=7)
    assert perf == {
        "window_days": 7, "total_contents": 0, "total_with_metrics": 0,
        "by_type": [], "by_style": [], "top_performers": [],
    }


def test_get_calendar_conflicts_returns_overlapping_events(store):
    cid = store.save_content(GeneratedContent(
        title="A", content="b", content_type=ContentType.XIAOHONGSHU,
    ))
    d1 = date.today()
    d2 = d1 + timedelta(days=2)
    d3 = d1 + timedelta(days=10)
    store.save_calendar_event(cid, "xiaohongshu", d1)
    store.save_calendar_event(cid, "xiaohongshu", d2)
    store.save_calendar_event(cid, "xiaohongshu", d3)

    conflicts = store.get_calendar_conflicts(d1, d2)
    assert len(conflicts) == 2
    assert all(c["platform"] == "xiaohongshu" for c in conflicts)
    # d3 is outside the window
    assert all(c["scheduled_date"] != d3.isoformat() for c in conflicts)


def test_list_optimization_candidates_underperforming(store):
    winner_id = store.save_content(GeneratedContent(
        title="winner", content="b", content_type=ContentType.XIAOHONGSHU,
    ))
    weak_id = store.save_content(GeneratedContent(
        title="weak", content="b", content_type=ContentType.XIAOHONGSHU,
    ))
    session = store._get_session()
    try:
        session.add_all([
            ContentMetrics(content_id=winner_id, platform="xiaohongshu",
                           views=10000, likes=1500, comments=200, shares=200),
            ContentMetrics(content_id=weak_id, platform="xiaohongshu",
                           views=10000, likes=50, comments=5, shares=2),
        ])
        session.commit()
    finally:
        session.close()

    candidates = store.list_optimization_candidates("underperforming", limit=5)
    assert len(candidates) == 1
    assert candidates[0]["id"] == weak_id
    assert candidates[0]["engagement_rate"] < candidates[0]["global_avg_rate"]


def test_list_optimization_candidates_old_drafts(store):
    old_id = store.save_content(GeneratedContent(
        title="old draft", content="b", content_type=ContentType.XIAOHONGSHU,
    ))
    # Backdate via direct ORM update.
    session = store._get_session()
    try:
        from src.storage.content_store import Content as ContentModel
        row = session.query(ContentModel).filter(ContentModel.id == old_id).first()
        row.created_at = datetime.now() - timedelta(days=20)
        session.commit()
    finally:
        session.close()
    # Fresh draft should NOT show up under old_drafts.
    store.save_content(GeneratedContent(
        title="fresh draft", content="b", content_type=ContentType.XIAOHONGSHU,
    ))

    candidates = store.list_optimization_candidates("old_drafts", limit=5)
    ids = [c["id"] for c in candidates]
    assert old_id in ids
    assert all(c["age_days"] >= 14 for c in candidates)
