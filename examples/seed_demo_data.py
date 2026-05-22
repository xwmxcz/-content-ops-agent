"""Seed local demo data without calling external LLM APIs.

Generates ~50 content rows across 6 topical domains plus realistic engagement
metrics (exponential distribution: a few hits, lots of average) so the chat
Agent's analyze_content_performance / propose_topics tools have real signal
to work with. Idempotent: deletes only rows tagged with the demo provider.
"""
from __future__ import annotations

import argparse
import json
import random
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


SPECS: list[dict[str, Any]] = [
    # ---- 科技数码 (10) ------------------------------------------------------
    {"title": "ChatGPT vs Claude vs Gemini：内容运营场景下的实战对比",
     "domain": "tech", "content_type": "blog", "style": "professional",
     "keywords": ["AI对比", "ChatGPT", "Claude"], "tags": ["AI工具", "横评"],
     "created_days": -2, "engagement": "high"},
    {"title": "我把团队的选题会换成了 AI Agent，效率提升 3 倍",
     "domain": "tech", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["AI Agent", "效率", "工作流"], "tags": ["AI", "效率工具"],
     "created_days": -5, "engagement": "viral"},
    {"title": "5 款被低估的生产力 App，最后一个我用了 3 年",
     "domain": "tech", "content_type": "xiaohongshu", "style": "casual",
     "keywords": ["生产力", "App推荐"], "tags": ["效率工具"],
     "created_days": -8, "engagement": "high"},
    {"title": "Notion AI 实测：哪些功能值得开会员",
     "domain": "tech", "content_type": "blog", "style": "professional",
     "keywords": ["Notion", "AI", "效率"], "tags": ["Notion", "笔记软件"],
     "created_days": -12, "engagement": "medium"},
    {"title": "MacBook Pro M4 一周开箱：写代码到底快多少",
     "domain": "tech", "content_type": "xiaohongshu", "style": "casual",
     "keywords": ["MacBook", "M4", "开发者"], "tags": ["数码开箱"],
     "created_days": -14, "engagement": "high"},
    {"title": "用 Cursor 写了一个月代码：值得你抛弃 VS Code 吗",
     "domain": "tech", "content_type": "blog", "style": "casual",
     "keywords": ["Cursor", "AI编程"], "tags": ["开发工具", "AI编程"],
     "created_days": -18, "engagement": "high"},
    {"title": "Why Local LLMs Are Quietly Winning the Privacy Battle",
     "domain": "tech", "content_type": "twitter", "style": "marketing",
     "keywords": ["LLM", "privacy", "open source"], "tags": ["LLM", "open-source"],
     "created_days": -20, "engagement": "medium"},
    {"title": "短视频脚本：办公桌上的 AI 工作站",
     "domain": "tech", "content_type": "video_script", "style": "storytelling",
     "keywords": ["AI", "办公", "工作站"], "tags": ["短视频"],
     "created_days": -22, "engagement": "low"},
    {"title": "3 分钟搞懂：什么是 Agentic AI",
     "domain": "tech", "content_type": "weibo", "style": "casual",
     "keywords": ["Agent", "AI入门"], "tags": ["科普"],
     "created_days": -28, "engagement": "high"},
    {"title": "我的 AI 选题工作流：从灵感到发布全自动",
     "domain": "tech", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["AI", "选题", "自动化"], "tags": ["内容运营", "AI工作流"],
     "created_days": -35, "engagement": "viral"},

    # ---- 职场成长 (10) ------------------------------------------------------
    {"title": "远程办公 3 年，我总结的 5 条铁律",
     "domain": "career", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["远程办公", "职场"], "tags": ["远程", "职场成长"],
     "created_days": -3, "engagement": "high"},
    {"title": "副业从 0 到月入 5K：我踩过的 3 个坑",
     "domain": "career", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["副业", "自由职业"], "tags": ["副业", "成长"],
     "created_days": -6, "engagement": "viral"},
    {"title": "面试 30 家公司后，我学到的简历真相",
     "domain": "career", "content_type": "blog", "style": "professional",
     "keywords": ["简历", "面试", "求职"], "tags": ["求职", "面试技巧"],
     "created_days": -9, "engagement": "high"},
    {"title": "微博碎碎念：今天又被 PUA 了",
     "domain": "career", "content_type": "weibo", "style": "casual",
     "keywords": ["职场", "情绪"], "tags": ["职场吐槽"],
     "created_days": -11, "engagement": "medium"},
    {"title": "毕业 3 年涨薪 200%：背后的 4 个底层逻辑",
     "domain": "career", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["涨薪", "职场跃迁"], "tags": ["成长", "薪资"],
     "created_days": -15, "engagement": "high"},
    {"title": "How I Stopped Overworking and Got Promoted",
     "domain": "career", "content_type": "twitter", "style": "marketing",
     "keywords": ["productivity", "burnout"], "tags": ["career", "productivity"],
     "created_days": -19, "engagement": "low"},
    {"title": "短视频脚本：和老板提加薪的正确话术",
     "domain": "career", "content_type": "video_script", "style": "storytelling",
     "keywords": ["加薪", "谈判"], "tags": ["职场技巧"],
     "created_days": -23, "engagement": "medium"},
    {"title": "30 岁转行做产品经理，我后悔了吗",
     "domain": "career", "content_type": "blog", "style": "storytelling",
     "keywords": ["转行", "产品经理"], "tags": ["职业转换"],
     "created_days": -27, "engagement": "medium"},
    {"title": "下班后 2 小时怎么过，决定 5 年后的差距",
     "domain": "career", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["自我提升", "时间管理"], "tags": ["成长"],
     "created_days": -33, "engagement": "high"},
    {"title": "从 985 毕业到失业 3 个月：我做错了什么",
     "domain": "career", "content_type": "weibo", "style": "storytelling",
     "keywords": ["失业", "求职"], "tags": ["职场"],
     "created_days": -42, "engagement": "low"},

    # ---- 生活方式 (12) ------------------------------------------------------
    {"title": "周末徒步避坑指南：北京近郊 5 条路线",
     "domain": "lifestyle", "content_type": "xiaohongshu", "style": "casual",
     "keywords": ["徒步", "北京", "户外"], "tags": ["徒步", "周末"],
     "created_days": -1, "engagement": "high"},
    {"title": "300 块的露营装备清单，新手照抄就行",
     "domain": "lifestyle", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["露营", "装备", "新手"], "tags": ["露营", "户外"],
     "created_days": -4, "engagement": "viral"},
    {"title": "改造 12㎡ 出租屋，预算 2000",
     "domain": "lifestyle", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["出租屋", "改造", "家居"], "tags": ["家居", "改造"],
     "created_days": -7, "engagement": "high"},
    {"title": "试了一周纯素饮食，我有这些感受",
     "domain": "lifestyle", "content_type": "weibo", "style": "casual",
     "keywords": ["素食", "饮食实验"], "tags": ["饮食", "健康"],
     "created_days": -10, "engagement": "medium"},
    {"title": "在家做手冲咖啡：从 19 块的雀巢到月花 200 的入坑路",
     "domain": "lifestyle", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["咖啡", "手冲", "入坑"], "tags": ["咖啡", "生活方式"],
     "created_days": -13, "engagement": "viral"},
    {"title": "花 50 改造书桌：把生产力提升 3 倍的小物清单",
     "domain": "lifestyle", "content_type": "xiaohongshu", "style": "casual",
     "keywords": ["书桌", "生产力", "改造"], "tags": ["家居", "生产力"],
     "created_days": -16, "engagement": "high"},
    {"title": "骑行 100 公里我学到的 4 件事",
     "domain": "lifestyle", "content_type": "blog", "style": "storytelling",
     "keywords": ["骑行", "户外"], "tags": ["骑行", "运动"],
     "created_days": -21, "engagement": "medium"},
    {"title": "短视频脚本：一天的 minimal 生活 vlog",
     "domain": "lifestyle", "content_type": "video_script", "style": "storytelling",
     "keywords": ["简约", "vlog"], "tags": ["vlog", "生活方式"],
     "created_days": -25, "engagement": "low"},
    {"title": "Why I Started Walking 10K Steps a Day",
     "domain": "lifestyle", "content_type": "twitter", "style": "marketing",
     "keywords": ["walking", "health"], "tags": ["health", "lifestyle"],
     "created_days": -29, "engagement": "low"},
    {"title": "周末烘焙：第一次做戚风蛋糕的失败实录",
     "domain": "lifestyle", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["烘焙", "蛋糕"], "tags": ["烘焙", "周末"],
     "created_days": -34, "engagement": "medium"},
    {"title": "买了健身环 3 个月，瘦了 8 斤是真的吗",
     "domain": "lifestyle", "content_type": "xiaohongshu", "style": "casual",
     "keywords": ["健身环", "减肥"], "tags": ["健身", "Switch"],
     "created_days": -40, "engagement": "high"},
    {"title": "在家养了一个月猫，我后悔了 100 次又爱了 1000 次",
     "domain": "lifestyle", "content_type": "weibo", "style": "storytelling",
     "keywords": ["养猫", "宠物"], "tags": ["宠物"],
     "created_days": -47, "engagement": "viral"},

    # ---- 金融理财 (8) -------------------------------------------------------
    {"title": "存钱 5 万的 4 个真实方法，没一个是省咖啡钱",
     "domain": "finance", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["存钱", "理财"], "tags": ["理财", "存钱"],
     "created_days": -2, "engagement": "viral"},
    {"title": "工资 1 万怎么分配：我用了 3 年的极简理财表",
     "domain": "finance", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["理财", "工资", "预算"], "tags": ["理财", "工资分配"],
     "created_days": -8, "engagement": "high"},
    {"title": "基金亏麻了：从亏 30% 到回本的两个动作",
     "domain": "finance", "content_type": "blog", "style": "storytelling",
     "keywords": ["基金", "亏损", "回本"], "tags": ["基金", "投资"],
     "created_days": -14, "engagement": "high"},
    {"title": "消费降级一年：我省下了 4 万",
     "domain": "finance", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["消费降级", "存钱"], "tags": ["理财"],
     "created_days": -19, "engagement": "viral"},
    {"title": "23 岁第一次买保险：买什么、避什么",
     "domain": "finance", "content_type": "blog", "style": "professional",
     "keywords": ["保险", "新手"], "tags": ["保险", "理财"],
     "created_days": -26, "engagement": "medium"},
    {"title": "How I Save 30% of My Income on a $50K Salary",
     "domain": "finance", "content_type": "twitter", "style": "marketing",
     "keywords": ["personal finance", "saving"], "tags": ["finance"],
     "created_days": -31, "engagement": "low"},
    {"title": "短视频脚本：3 个让你穷一辈子的金钱观",
     "domain": "finance", "content_type": "video_script", "style": "marketing",
     "keywords": ["金钱观", "理财"], "tags": ["短视频", "理财"],
     "created_days": -36, "engagement": "medium"},
    {"title": "记账 365 天后，我看清了自己花钱的 3 个真相",
     "domain": "finance", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["记账", "消费习惯"], "tags": ["理财"],
     "created_days": -45, "engagement": "high"},

    # ---- 餐饮探店 (6) -------------------------------------------------------
    {"title": "上海 50 块吃饱的 5 家店：本地人推荐",
     "domain": "food", "content_type": "xiaohongshu", "style": "casual",
     "keywords": ["上海", "美食", "平价"], "tags": ["上海", "探店"],
     "created_days": -3, "engagement": "viral"},
    {"title": "北京胡同里的咖啡店地图，我私藏了 3 年",
     "domain": "food", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["北京", "咖啡店", "胡同"], "tags": ["北京", "咖啡"],
     "created_days": -10, "engagement": "high"},
    {"title": "测评了 10 家精品咖啡，最贵的不一定最好",
     "domain": "food", "content_type": "blog", "style": "professional",
     "keywords": ["咖啡", "测评"], "tags": ["咖啡", "评测"],
     "created_days": -17, "engagement": "high"},
    {"title": "周末逛吃 vlog：在成都吃了 8 顿",
     "domain": "food", "content_type": "video_script", "style": "storytelling",
     "keywords": ["成都", "美食", "vlog"], "tags": ["美食", "vlog"],
     "created_days": -24, "engagement": "medium"},
    {"title": "上班族的工作日午餐：30 块吃饱不踩雷",
     "domain": "food", "content_type": "xiaohongshu", "style": "casual",
     "keywords": ["午餐", "上班族", "平价"], "tags": ["午餐", "上班族"],
     "created_days": -32, "engagement": "high"},
    {"title": "广州早茶第一站：阿婆推荐这 3 家",
     "domain": "food", "content_type": "weibo", "style": "casual",
     "keywords": ["广州", "早茶"], "tags": ["广州", "美食"],
     "created_days": -41, "engagement": "medium"},

    # ---- 教育学习 (4) -------------------------------------------------------
    {"title": "0 基础学 Python：我用了 90 天，给你看真实路径",
     "domain": "education", "content_type": "blog", "style": "storytelling",
     "keywords": ["Python", "入门", "学习"], "tags": ["编程", "学习"],
     "created_days": -6, "engagement": "viral"},
    {"title": "考下 PMP 的人都做对了什么：3 条复盘",
     "domain": "education", "content_type": "xiaohongshu", "style": "professional",
     "keywords": ["PMP", "考证"], "tags": ["考证", "项目管理"],
     "created_days": -16, "engagement": "high"},
    {"title": "今年我读完的 12 本书，3 本我会反复读",
     "domain": "education", "content_type": "xiaohongshu", "style": "storytelling",
     "keywords": ["读书", "推荐"], "tags": ["读书", "成长"],
     "created_days": -28, "engagement": "high"},
    {"title": "5 个让英语口语真的变好的笨办法",
     "domain": "education", "content_type": "weibo", "style": "casual",
     "keywords": ["英语", "口语", "学习方法"], "tags": ["英语"],
     "created_days": -38, "engagement": "medium"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo data for the Content Ops prototype.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible metrics.")
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


# Engagement tier → (views_lo, views_hi, like_rate_pct, comment_rate_pct, share_rate_pct)
ENGAGEMENT_TIERS = {
    "viral":  (15000, 60000, 8.0, 1.2, 1.8),
    "high":   (5000,  15000, 5.5, 0.8, 0.9),
    "medium": (1500,  5000,  3.5, 0.5, 0.4),
    "low":    (300,   1500,  2.0, 0.3, 0.2),
}


def _generate_metrics(rng: random.Random, tier: str, platform: str) -> dict[str, int]:
    lo, hi, like_rate, comment_rate, share_rate = ENGAGEMENT_TIERS[tier]
    views = rng.randint(lo, hi)
    # Add jitter so two posts in same tier don't look identical.
    likes = int(views * like_rate / 100 * rng.uniform(0.8, 1.2))
    comments = int(views * comment_rate / 100 * rng.uniform(0.7, 1.3))
    shares = int(views * share_rate / 100 * rng.uniform(0.6, 1.4))
    return {"views": views, "likes": likes, "comments": comments, "shares": shares}


def _body_for(spec: dict[str, Any]) -> str:
    title = spec["title"]
    style = spec["style"]
    if style == "professional":
        return (
            f"# {title}\n\n"
            "1. 先看用户实际的行为数据，再决定下一步要做什么。\n"
            "2. 把每个判断写下来，方便复盘。\n"
            "3. 内容运营不是灵感游戏，是稳定的流程。\n"
        )
    if style == "storytelling":
        return (
            f"那天我决定写下《{title}》的初稿。\n\n"
            "起因很简单 —— 朋友又来问我同一个问题。我一边解释，一边意识到这本来就该写下来。\n"
            "于是有了这篇内容。希望对正在踩同样坑的你有用。"
        )
    if style == "marketing":
        return (
            f"{title}\n\n"
            "Three takeaways inside. Save this if you don't have time to read it now."
        )
    return (
        f"{title}\n\n"
        "随手记一下，希望对你有用。如果你也有类似经验，留言交流。"
    )


def seed_content_rows(store: ContentStore, seed: int) -> tuple[list[Content], int]:
    rng = random.Random(seed)
    today = date.today()
    now = datetime.now()
    session = store._get_session()
    try:
        rows: list[Content] = []
        metric_count = 0
        for spec in SPECS:
            created_at = datetime.combine(today + timedelta(days=spec["created_days"]), now.time())
            # Token usage and cost are rough estimates so the demo dashboard has data.
            length_factor = {"professional": 1.4, "storytelling": 1.6, "casual": 1.0, "marketing": 0.8}[spec["style"]]
            token_usage = int(rng.randint(700, 1800) * length_factor)
            cost_estimate = round(token_usage / 1000 * rng.uniform(0.05, 0.18), 3)
            row = Content(
                title=spec["title"],
                content=_body_for(spec),
                content_type=spec["content_type"],
                style=spec["style"],
                keywords=json.dumps(spec["keywords"], ensure_ascii=False),
                tags=json.dumps(spec["tags"], ensure_ascii=False),
                status=rng.choice(["published", "published", "published", "draft", "refined"]),
                version=1,
                llm_provider=DEMO_PROVIDER,
                model_name=DEMO_MODEL,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(row)
            rows.append(row)

        session.flush()

        # 70% of rows get metrics — closer to real life where not everything gets tracked.
        scheduled_dates: set[tuple[str, str]] = set()
        for spec, row in zip(SPECS, rows):
            if rng.random() < 0.7:
                m = _generate_metrics(rng, spec["engagement"], spec["content_type"])
                session.add(ContentMetrics(
                    content_id=row.id,
                    platform=spec["content_type"],
                    views=m["views"],
                    likes=m["likes"],
                    comments=m["comments"],
                    shares=m["shares"],
                    recorded_at=row.created_at + timedelta(days=2),
                ))
                metric_count += 1

            # Schedule 6 of the most recent items into the next 14 days for the calendar.
            if spec["created_days"] >= -14 and len(scheduled_dates) < 6:
                offset = len(scheduled_dates) * 2 + 1  # spread across upcoming days
                slot = today + timedelta(days=offset)
                key = (slot.isoformat(), spec["content_type"])
                if key not in scheduled_dates:
                    scheduled_dates.add(key)
                    session.add(CalendarEvent(
                        content_id=row.id,
                        platform=spec["content_type"],
                        scheduled_date=slot,
                        status="planned",
                    ))

        session.commit()
        return rows, metric_count
    finally:
        session.close()


def seed_agent_thread(store: ContentStore) -> None:
    now = datetime.now()
    tool_events = [
        {"name": "analyze_content_performance", "args": {"days": 30}, "status": "completed",
         "output": "Aggregated 30-day performance grouped by content_type and style."},
        {"name": "propose_topics", "args": {"count": 5}, "status": "completed",
         "output": "Returned a topic brief with winning content types and recent titles to avoid."},
    ]
    session = store._get_session()
    try:
        thread = AgentThread(
            id=DEMO_THREAD_ID,
            title="Demo: 选题建议 + 周排期",
            last_provider=DEMO_PROVIDER,
            last_model=DEMO_MODEL,
            created_at=now,
            updated_at=now,
        )
        session.add(thread)
        session.add_all([
            AgentMessage(
                thread_id=DEMO_THREAD_ID, role="user",
                content="看一下我们最近 30 天发的内容表现，给我推 5 个下周该写的选题。",
                provider=DEMO_PROVIDER, model=DEMO_MODEL, status="completed", created_at=now,
            ),
            AgentMessage(
                thread_id=DEMO_THREAD_ID, role="assistant",
                content=(
                    "我先用 analyze_content_performance 看了过去 30 天 35 篇带数据的内容，"
                    "再用 propose_topics 拿到选题情报。综合下来 5 个建议（详见 markdown 表）。"
                    "确认后我可以再帮你 propose 一份周一三五的发布排期。"
                ),
                provider=DEMO_PROVIDER, model=DEMO_MODEL,
                tool_events=json.dumps(tool_events, ensure_ascii=False),
                status="completed", created_at=now,
            ),
        ])
        session.commit()
    finally:
        session.close()


def main() -> None:
    args = parse_args()
    store = build_store(args)
    reset_demo_rows(store)
    rows, metric_count = seed_content_rows(store, args.seed)
    seed_agent_thread(store)

    stats = store.get_content_stats()
    perf = store.aggregate_performance(60)
    print("Seeded demo data successfully.")
    print(f"Content rows:     {len(rows)}")
    print(f"With metrics:     {metric_count}")
    print(f"Calendar events:  {min(6, len(rows))}")
    print(f"Agent threads:    1")
    print(f"Stats:            {json.dumps(stats, ensure_ascii=False)}")
    print(f"60d performance:  {len(perf['by_type'])} content_types, top performer = "
          f"{(perf['top_performers'][0]['title'] if perf['top_performers'] else 'n/a')}")


if __name__ == "__main__":
    main()
