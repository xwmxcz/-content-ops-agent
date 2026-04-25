"""Seed local demo data without calling external LLM APIs.

The script is intentionally idempotent: it deletes only rows that were created
by this demo seed marker, then inserts fresh content, calendar events, metrics,
and one persisted Agent chat thread.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage.content_store import (  # noqa: E402
    AgentMessage,
    AgentThread,
    CalendarEvent,
    Content,
    ContentMetrics,
    ContentStore,
)
from src.utils import config  # noqa: E402


DEMO_PROVIDER = "demo"
DEMO_MODEL = "seed-data-v1"
DEMO_THREAD_ID = "demo-content-ops-thread"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo data for the Content Ops prototype.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL to seed. Defaults to DATABASE_URL from .env/config.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite file path to seed when --database-url is not provided.",
    )
    return parser.parse_args()


def build_store(args: argparse.Namespace) -> ContentStore:
    if args.database_url:
        return ContentStore(database_url=args.database_url)
    if args.db_path:
        return ContentStore(db_path=args.db_path)
    return ContentStore(database_url=config.DATABASE_URL)


def reset_demo_rows(store: ContentStore) -> None:
    session = store._get_session()
    try:
        demo_content_ids = [
            row[0]
            for row in session.query(Content.id)
            .filter(Content.llm_provider == DEMO_PROVIDER, Content.model_name == DEMO_MODEL)
            .all()
        ]
        if demo_content_ids:
            session.query(CalendarEvent).filter(CalendarEvent.content_id.in_(demo_content_ids)).delete(
                synchronize_session=False
            )
            session.query(ContentMetrics).filter(ContentMetrics.content_id.in_(demo_content_ids)).delete(
                synchronize_session=False
            )
            session.query(Content).filter(Content.id.in_(demo_content_ids)).delete(synchronize_session=False)

        session.query(AgentMessage).filter(AgentMessage.thread_id == DEMO_THREAD_ID).delete(synchronize_session=False)
        session.query(AgentThread).filter(AgentThread.id == DEMO_THREAD_ID).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def seed_content_rows(store: ContentStore) -> list[Content]:
    today = date.today()
    now = datetime.now()
    specs: list[dict[str, Any]] = [
        {
            "title": "AI 内容工作台上线预热：从灵感到复盘的一条线",
            "content": (
                "过去我们把选题、写作、润色和复盘拆在不同工具里，信息很容易断掉。\n\n"
                "现在可以把主题输入、策略拆解、初稿生成、编辑审核、日历排期放在同一个工作台。"
                "团队不需要追逐每一个新模型，而是先把内容流程标准化。"
            ),
            "content_type": "xiaohongshu",
            "style": "professional",
            "keywords": ["AI", "内容运营", "工作流"],
            "tags": ["AI内容运营", "效率工具", "内容工作台"],
            "status": "draft",
            "created_days": -4,
            "token_usage": 1840,
            "cost_estimate": 0.18,
        },
        {
            "title": "3 步建立稳定选题池",
            "content": (
                "选题不是灵感游戏。\n"
                "1. 把用户问题归类。\n"
                "2. 把每类问题拆成内容角度。\n"
                "3. 每周复盘点击、收藏和转化。\n"
                "AI 适合做扩展和初筛，人负责判断优先级。"
            ),
            "content_type": "weibo",
            "style": "casual",
            "keywords": ["选题", "内容团队", "复盘"],
            "tags": ["选题池", "内容复盘"],
            "status": "published",
            "created_days": -3,
            "token_usage": 860,
            "cost_estimate": 0.08,
        },
        {
            "title": "内容团队如何把 AI 从玩具变成流程",
            "content": (
                "真正有价值的 AI 内容系统不是只会生成一段文案，而是把策略、写作、编辑、审核和沉淀串起来。"
                "当每一次输出都能保存、打磨、排期和复盘，AI 才会变成团队资产。"
            ),
            "content_type": "blog",
            "style": "professional",
            "keywords": ["AI", "团队协作", "SOP"],
            "tags": ["Agent", "SaaS原型", "内容系统"],
            "status": "refined",
            "created_days": -2,
            "token_usage": 2360,
            "cost_estimate": 0.24,
        },
        {
            "title": "短视频脚本：AI 内容周会",
            "content": (
                "开场：你的一周内容会是不是还在靠临时想？\n"
                "镜头一：展示选题池和历史内容。\n"
                "镜头二：让 Agent 生成策略和初稿。\n"
                "镜头三：把最终稿加入发布日历。\n"
                "结尾：让 AI 做流程助手，而不是替代团队判断。"
            ),
            "content_type": "video_script",
            "style": "storytelling",
            "keywords": ["短视频", "内容周会", "AI工作流"],
            "tags": ["短视频脚本", "团队效率"],
            "status": "draft",
            "created_days": -1,
            "token_usage": 1540,
            "cost_estimate": 0.14,
        },
        {
            "title": "Ship content ops, not prompt demos",
            "content": (
                "Prompt demos are easy. Content operations are harder: persistence, review loops, calendar planning, "
                "model routing, and traceable tool calls. That is where LLM apps start feeling like real products."
            ),
            "content_type": "twitter",
            "style": "marketing",
            "keywords": ["LLM apps", "Agents", "product"],
            "tags": ["LLM", "Agent", "SaaS"],
            "status": "published",
            "created_days": -1,
            "token_usage": 620,
            "cost_estimate": 0.06,
        },
        {
            "title": "复盘模板：让爆款经验沉淀为流程",
            "content": (
                "每条内容发布后记录 4 件事：目标人群、核心钩子、互动最高的段落、下一次可以复用的结构。"
                "复盘不是写总结，而是把经验变成下一次创作的输入。"
            ),
            "content_type": "xiaohongshu",
            "style": "professional",
            "keywords": ["复盘", "模板", "内容增长"],
            "tags": ["内容复盘", "增长实验"],
            "status": "archived",
            "created_days": -7,
            "token_usage": 1120,
            "cost_estimate": 0.11,
        },
    ]

    session = store._get_session()
    try:
        rows: list[Content] = []
        for spec in specs:
            created_at = datetime.combine(today + timedelta(days=spec["created_days"]), now.time())
            row = Content(
                title=spec["title"],
                content=spec["content"],
                content_type=spec["content_type"],
                style=spec["style"],
                keywords=json.dumps(spec["keywords"], ensure_ascii=False),
                tags=json.dumps(spec["tags"], ensure_ascii=False),
                status=spec["status"],
                version=1,
                llm_provider=DEMO_PROVIDER,
                model_name=DEMO_MODEL,
                token_usage=spec["token_usage"],
                cost_estimate=spec["cost_estimate"],
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(row)
            rows.append(row)

        session.flush()
        rows[2].parent_id = rows[0].id

        events = [
            CalendarEvent(content_id=rows[0].id, platform="xiaohongshu", scheduled_date=today + timedelta(days=1)),
            CalendarEvent(content_id=rows[2].id, platform="blog", scheduled_date=today + timedelta(days=2)),
            CalendarEvent(content_id=rows[3].id, platform="video_script", scheduled_date=today + timedelta(days=3)),
            CalendarEvent(content_id=rows[4].id, platform="twitter", scheduled_date=today + timedelta(days=4)),
            CalendarEvent(content_id=rows[1].id, platform="weibo", scheduled_date=today + timedelta(days=5)),
        ]
        session.add_all(events)

        metrics = [
            ContentMetrics(
                content_id=rows[1].id,
                platform="weibo",
                views=12800,
                likes=640,
                comments=86,
                shares=112,
            ),
            ContentMetrics(
                content_id=rows[4].id,
                platform="twitter",
                views=9400,
                likes=510,
                comments=44,
                shares=95,
            ),
        ]
        session.add_all(metrics)
        session.commit()
        return rows
    finally:
        session.close()


def seed_agent_thread(store: ContentStore) -> None:
    now = datetime.now()
    tool_events = [
        {
            "name": "list_recent_contents",
            "args": {"limit": 5},
            "output": "Returned 5 recent demo content items from the local content library.",
            "status": "completed",
            "error": None,
        },
        {
            "name": "view_calendar",
            "args": {"days": 7},
            "output": "Returned 5 planned demo publishing events for the next 7 days.",
            "status": "completed",
            "error": None,
        },
        {
            "name": "get_content_stats",
            "args": {},
            "output": "Returned content counts by type and status from the seeded local database.",
            "status": "completed",
            "error": None,
        },
    ]

    session = store._get_session()
    try:
        thread = AgentThread(
            id=DEMO_THREAD_ID,
            title="Demo: content operations weekly plan",
            last_provider=DEMO_PROVIDER,
            last_model=DEMO_MODEL,
            created_at=now,
            updated_at=now,
        )
        session.add(thread)
        session.add_all(
            [
                AgentMessage(
                    thread_id=DEMO_THREAD_ID,
                    role="user",
                    content="请查看最近内容、发布日历和统计数据，帮我总结本周内容运营重点。",
                    provider=DEMO_PROVIDER,
                    model=DEMO_MODEL,
                    status="completed",
                    created_at=now,
                ),
                AgentMessage(
                    thread_id=DEMO_THREAD_ID,
                    role="assistant",
                    content=(
                        "我已读取本地内容库、未来 7 天发布计划和统计数据。建议本周演示重点放在："
                        "1. 用 4-stage pipeline 生成高质量初稿；2. 用内容库展示可追溯沉淀；"
                        "3. 用日历和统计说明内容生命周期已经闭环。"
                    ),
                    provider=DEMO_PROVIDER,
                    model=DEMO_MODEL,
                    tool_events=json.dumps(tool_events, ensure_ascii=False),
                    status="completed",
                    created_at=now,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()


def main() -> None:
    args = parse_args()
    store = build_store(args)
    reset_demo_rows(store)
    rows = seed_content_rows(store)
    seed_agent_thread(store)

    stats = store.get_content_stats()
    print("Seeded demo data successfully.")
    print(f"Content rows: {len(rows)}")
    print("Calendar events: 5")
    print("Agent threads: 1")
    print(f"Stats: {json.dumps(stats, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
