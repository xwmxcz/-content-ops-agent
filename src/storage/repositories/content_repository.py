"""Content drafts, their variants, search, and the analytics built on them.

The aggregate queries here (``get_content_stats``, ``aggregate_performance``,
``list_optimization_candidates``) read content alongside its metrics; they are
grouped with content rather than metrics because content is the subject and the
metrics only decorate it."""

import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, or_

from src.storage.models import (
    CalendarEvent,
    Content,
    ContentMetrics,
    MediaAsset,
    PlatformPublication,
)
from src.storage.repositories.base import ILIKE_ESCAPE, RepositoryMixin, assigned_pk, ilike_contains_pattern
from src.storage.repositories.media_repository import MediaRepositoryMixin

logger = logging.getLogger(__name__)


class ContentEditConflict(ValueError):
    """The local draft changed after the editor loaded it."""


class ContentRepositoryMixin(MediaRepositoryMixin, RepositoryMixin):
    """Content, plus the media serializer that ``delete_content`` reports.

    See :class:`src.storage.content_store.ContentStore` for the shared contract.
    Mixed into ``ContentStore``; ``_get_session`` and ``user_id`` come from the
    host class, which is why this is a mixin rather than a standalone object.
    """

    def save_content(
        self,
        generated_content,
        llm_provider=None,
        model_name=None,
        parent_id=None,
        style: str = "casual",
        keywords: list[str] | None = None,
        token_usage: int | None = None,
        cost_estimate: float | None = None,
    ) -> int:
        session = self._get_session()
        try:
            if keywords is None and generated_content.metadata:
                keywords = generated_content.metadata.get("keywords", [])
            content = Content(
                title=generated_content.title,
                content=generated_content.content,
                content_type=generated_content.content_type.value if generated_content.content_type else "unknown",
                style=style,
                keywords=json.dumps(keywords or [], ensure_ascii=False),
                tags=json.dumps(generated_content.tags or []),
                status="draft",
                parent_id=parent_id,
                llm_provider=llm_provider,
                model_name=model_name,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
            )
            session.add(content)
            session.commit()
            return assigned_pk(content, "id")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_content(self, content_id: int) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            content = session.query(Content).filter(Content.id == content_id).first()
            if not content:
                return None
            return self._content_to_dict(content)
        finally:
            session.close()

    def update_content(self, content_id: int, **fields) -> bool:
        session = self._get_session()
        try:
            content = session.query(Content).filter(Content.id == content_id).first()
            if not content:
                return False
            for key, value in fields.items():
                if hasattr(content, key):
                    setattr(content, key, value)
            content.updated_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def edit_content(
        self, content_id: int, *, title: str, content: str, tags: list[str], expected_updated_at: str | None
    ) -> dict[str, Any] | None:
        with self._get_session() as session:
            row = session.query(Content).filter(Content.id == content_id).with_for_update().first()
            if row is None:
                return None
            current_token = row.updated_at.isoformat() if row.updated_at else None
            if current_token != expected_updated_at:
                raise ContentEditConflict("内容已被其他操作更新，请重新加载后再保存。当前编辑内容仍保留。")
            row.title = title
            row.content = content
            row.tags = json.dumps(tags, ensure_ascii=False)
            row.version = (row.version or 1) + 1
            row.updated_at = (
                max(datetime.now(), row.updated_at + timedelta(microseconds=1)) if row.updated_at else datetime.now()
            )
            session.commit()
            return self._content_to_dict(row)

    def restore_content(self, content_id: int) -> dict[str, Any] | None:
        """Explicitly restore an archive as a local draft; platform records stay intact."""
        with self._get_session() as session:
            row = session.query(Content).filter(Content.id == content_id).with_for_update().first()
            if row is None:
                return None
            if row.status != "archived":
                raise ContentEditConflict("只能将已归档内容恢复为草稿，请刷新后重试。")
            row.status = "draft"
            row.updated_at = datetime.now()
            session.commit()
            return self._content_to_dict(row)

    def list_contents(
        self, status=None, content_type=None, limit=50, offset=0, q: str | None = None
    ) -> list[dict[str, Any]]:
        session = self._get_session()
        try:
            query = session.query(Content)
            if status:
                query = query.filter(Content.status == status)
            if content_type:
                query = query.filter(Content.content_type == content_type)
            if q and q.strip():
                # Match literal text in the complete article before pagination
                # and preview truncation; '%' and '_' are not user wildcards.
                pattern = ilike_contains_pattern(q)
                query = query.filter(
                    or_(
                        Content.title.ilike(pattern, escape=ILIKE_ESCAPE),
                        Content.content.ilike(pattern, escape=ILIKE_ESCAPE),
                    )
                )
            query = query.order_by(Content.created_at.desc(), Content.id.desc()).limit(limit).offset(offset)
            contents = query.all()
            return [
                {
                    "id": c.id,
                    "title": c.title,
                    "content": c.content[:100] + "..." if len(c.content) > 100 else c.content,
                    "content_type": c.content_type,
                    "style": c.style,
                    "status": c.status,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in contents
            ]
        finally:
            session.close()

    def search_contents(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []
        pattern = ilike_contains_pattern(query)
        session = self._get_session()
        try:
            rows = (
                session.query(Content)
                .filter(
                    or_(
                        Content.title.ilike(pattern, escape=ILIKE_ESCAPE),
                        Content.content.ilike(pattern, escape=ILIKE_ESCAPE),
                        Content.keywords.ilike(pattern, escape=ILIKE_ESCAPE),
                    )
                )
                .order_by(Content.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._content_to_dict(c) for c in rows]
        finally:
            session.close()

    def get_content_stats(self) -> dict[str, Any]:
        session = self._get_session()
        try:
            total = session.query(Content).count()
            by_type = {
                content_type: count
                for content_type, count in (
                    session.query(Content.content_type, func.count(Content.id)).group_by(Content.content_type).all()
                )
                if content_type
            }
            by_status = {
                status: count
                for status, count in (
                    session.query(Content.status, func.count(Content.id)).group_by(Content.status).all()
                )
                if status
            }
            return {"total_contents": total, "by_type": by_type, "by_status": by_status}
        finally:
            session.close()

    def get_performance_stats(self, days: int = 30, platform: str | None = None) -> dict[str, Any]:
        """Current platform totals for a cohort defined by content creation date.

        Readings are cumulative and overwritten, so grouping by their upload
        date would invent a daily-growth series. The daily breakdown instead
        groups the latest readings by each content's creation date. Missing
        readings and recorded zero views remain distinguishable.
        """
        end = date.today()
        start = end - timedelta(days=days - 1)
        cutoff = datetime.combine(start, time.min)
        ceiling = datetime.combine(end + timedelta(days=1), time.min)
        platform = platform.strip().lower() if platform and platform.strip() else None

        def bucket() -> dict[str, Any]:
            return {"metric_rows": 0, "views": 0, "likes": 0, "comments": 0, "shares": 0}

        def finish(value: dict[str, Any]) -> dict[str, Any]:
            value["interactions"] = value["likes"] + value["comments"] + value["shares"]
            value["engagement_rate"] = round(value["interactions"] / value["views"], 4) if value["views"] else None
            return value

        with self._get_session() as session:
            # One statement gives the cohort and readings the same PostgreSQL
            # snapshot. DISTINCT ON keeps the latest reading per platform while
            # the outer join retains each content that has no recorded metrics.
            records = (
                session.query(Content.id, ContentMetrics, Content.title, Content.created_at)
                .select_from(Content)
                .outerjoin(ContentMetrics, ContentMetrics.content_id == Content.id)
                .filter(Content.created_at >= cutoff, Content.created_at < ceiling)
                .distinct(Content.id, ContentMetrics.platform)
                .order_by(
                    Content.id,
                    ContentMetrics.platform,
                    ContentMetrics.recorded_at.desc().nulls_last(),
                    ContentMetrics.id.desc(),
                )
                .all()
            )
            contents = {content_id: created_at for content_id, _, _, created_at in records}
            rows = [(metric, title, created_at) for _, metric, title, created_at in records if metric is not None]
            available_platforms = sorted({metric.platform or "unknown" for metric, _, _ in rows})
            totals = bucket()
            platforms: dict[str, dict[str, Any]] = {}
            cohorts: dict[str, dict[str, Any]] = {}
            measured: set[int] = set()
            measured_by_day: dict[str, set[int]] = {}
            performers = []
            latest_reading: datetime | None = None
            for index in range(days):
                day = (start + timedelta(days=index)).isoformat()
                cohorts[day] = {"date": day, "total_contents": 0, "measured_contents": 0, **bucket()}
                measured_by_day[day] = set()
            for created_at in contents.values():
                cohorts[created_at.date().isoformat()]["total_contents"] += 1
            for metric, title, created_at in rows:
                name = metric.platform or "unknown"
                if platform and name != platform:
                    continue
                day = created_at.date().isoformat()
                measured.add(metric.content_id)
                measured_by_day[day].add(metric.content_id)
                per_platform = platforms.setdefault(name, {"platform": name, **bucket()})
                for target in (totals, per_platform, cohorts[day]):
                    target["metric_rows"] += 1
                    for field in ("views", "likes", "comments", "shares"):
                        target[field] += getattr(metric, field) or 0
                if metric.recorded_at and (latest_reading is None or metric.recorded_at > latest_reading):
                    latest_reading = metric.recorded_at
                performers.append(
                    {
                        "content_id": metric.content_id,
                        "title": title,
                        "platform": name,
                        **finish(
                            {
                                "metric_rows": 1,
                                **{
                                    field: getattr(metric, field) or 0
                                    for field in ("views", "likes", "comments", "shares")
                                },
                            }
                        ),
                    }
                )
            for day, cohort in cohorts.items():
                cohort["measured_contents"] = len(measured_by_day[day])
                finish(cohort)
            return {
                "window_days": days,
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
                "platform": platform,
                "available_platforms": available_platforms,
                "total_contents": len(contents),
                "measured_contents": len(measured),
                "missing_contents": len(contents) - len(measured),
                "last_recorded_at": latest_reading.isoformat() if latest_reading else None,
                "totals": finish(totals),
                "by_platform": [finish(value) for _, value in sorted(platforms.items())],
                "by_creation_date": list(cohorts.values()),
                "top_contents": sorted(
                    performers,
                    key=lambda row: (-row["views"], -row["interactions"], row["content_id"], row["platform"]),
                )[:10],
            }

    @staticmethod
    def _latest_metrics_by_content(metrics_rows: list[ContentMetrics]) -> dict[int, ContentMetrics]:
        """Deduplicate readings by ``(content_id, platform)`` keeping the latest
        ``(recorded_at DESC NULLS LAST, id DESC)`` reading per platform, then sum
        across platforms per content so multi-platform articles match
        :meth:`get_performance_stats`.
        """
        latest_per_platform: dict[tuple[int, str], ContentMetrics] = {}

        def _order_key(row: ContentMetrics) -> tuple[bool, datetime, int]:
            return (row.recorded_at is not None, row.recorded_at or datetime.min, row.id or 0)

        for row in metrics_rows:
            if row.content_id is None:
                continue
            key = (row.content_id, (row.platform or "unknown").strip().lower() or "unknown")
            existing = latest_per_platform.get(key)
            if existing is None or _order_key(row) > _order_key(existing):
                latest_per_platform[key] = row

        aggregated: dict[int, ContentMetrics] = {}
        for (content_id, _platform), row in latest_per_platform.items():
            current = aggregated.get(content_id)
            if current is None:
                aggregated[content_id] = ContentMetrics(
                    content_id=content_id,
                    platform=row.platform,
                    views=row.views or 0,
                    likes=row.likes or 0,
                    comments=row.comments or 0,
                    shares=row.shares or 0,
                    recorded_at=row.recorded_at,
                )
            else:
                current.views = (current.views or 0) + (row.views or 0)
                current.likes = (current.likes or 0) + (row.likes or 0)
                current.comments = (current.comments or 0) + (row.comments or 0)
                current.shares = (current.shares or 0) + (row.shares or 0)
        return aggregated

    def aggregate_performance(self, days: int = 30) -> dict[str, Any]:
        """Group contents from the last `days` days by content_type + style and aggregate
        engagement metrics. Used by the chat Agent's analyze_content_performance tool.

        Returns a compact structure suitable for feeding into an LLM context (typically
        well under 2KB):

            {
              "window_days": 30,
              "total_contents": 47,
              "total_with_metrics": 23,
              "by_type": [{"content_type": "xiaohongshu", "count": 18, "avg_views": 4200,
                           "avg_likes": 210, "avg_engagement_rate": 0.052}, ...],
              "by_style": [...],
              "top_performers": [{"id": 12, "title": "...", "content_type": "xiaohongshu",
                                  "views": 18400, "likes": 1240, "engagement_rate": 0.067}, ...]
            }
        """
        cutoff = datetime.now() - timedelta(days=max(1, days))
        session = self._get_session()
        try:
            contents = session.query(Content).filter(Content.created_at >= cutoff).all()
            if not contents:
                return {
                    "window_days": days,
                    "total_contents": 0,
                    "total_with_metrics": 0,
                    "by_type": [],
                    "by_style": [],
                    "top_performers": [],
                }
            content_ids = [c.id for c in contents]
            metrics_rows = session.query(ContentMetrics).filter(ContentMetrics.content_id.in_(content_ids)).all()
            metrics_by_content = self._latest_metrics_by_content(metrics_rows)

            def _engagement_rate(m: ContentMetrics | None) -> float:
                if m is None or not m.views:
                    return 0.0
                return round(((m.likes or 0) + (m.comments or 0) + (m.shares or 0)) / m.views, 4)

            type_buckets: dict[str, dict[str, Any]] = {}
            style_buckets: dict[str, dict[str, Any]] = {}
            for content in contents:
                content_metrics = metrics_by_content.get(content.id)
                for bucket_key, store_dict in (
                    (content.content_type or "unknown", type_buckets),
                    (content.style or "unknown", style_buckets),
                ):
                    bucket = store_dict.setdefault(
                        bucket_key,
                        {
                            "count": 0,
                            "with_metrics": 0,
                            "views": 0,
                            "likes": 0,
                            "comments": 0,
                            "shares": 0,
                            "engagement_rates": [],
                        },
                    )
                    bucket["count"] += 1
                    if content_metrics is not None:
                        bucket["with_metrics"] += 1
                        bucket["views"] += content_metrics.views or 0
                        bucket["likes"] += content_metrics.likes or 0
                        bucket["comments"] += content_metrics.comments or 0
                        bucket["shares"] += content_metrics.shares or 0
                        bucket["engagement_rates"].append(_engagement_rate(content_metrics))

            def _summarize(buckets: dict[str, dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
                out = []
                for k, b in buckets.items():
                    n = max(1, b["with_metrics"])
                    out.append(
                        {
                            key_name: k,
                            "count": b["count"],
                            "with_metrics": b["with_metrics"],
                            "avg_views": round(b["views"] / n) if b["with_metrics"] else 0,
                            "avg_likes": round(b["likes"] / n) if b["with_metrics"] else 0,
                            "avg_comments": round(b["comments"] / n) if b["with_metrics"] else 0,
                            "avg_engagement_rate": (
                                round(sum(b["engagement_rates"]) / len(b["engagement_rates"]), 4)
                                if b["engagement_rates"]
                                else 0.0
                            ),
                        }
                    )
                out.sort(key=lambda r: (r["with_metrics"] > 0, r["avg_engagement_rate"]), reverse=True)
                return out

            scored: list[tuple[float, Content, ContentMetrics]] = []
            for c in contents:
                metrics_row = metrics_by_content.get(c.id)
                if metrics_row is None:
                    continue
                scored.append((_engagement_rate(metrics_row), c, metrics_row))
            scored.sort(key=lambda x: (x[0], x[2].views or 0), reverse=True)
            top_performers = [
                {
                    "id": c.id,
                    "title": c.title,
                    "content_type": c.content_type,
                    "style": c.style,
                    "views": m.views or 0,
                    "likes": m.likes or 0,
                    "comments": m.comments or 0,
                    "engagement_rate": rate,
                }
                for rate, c, m in scored[:5]
            ]

            return {
                "window_days": days,
                "total_contents": len(contents),
                "total_with_metrics": len(metrics_by_content),
                "by_type": _summarize(type_buckets, "content_type"),
                "by_style": _summarize(style_buckets, "style"),
                "top_performers": top_performers,
            }
        finally:
            session.close()

    def list_optimization_candidates(self, criteria: str = "underperforming", limit: int = 5) -> list[dict[str, Any]]:
        """Find contents that may benefit from refinement. Used by the chat Agent's
        find_optimization_candidates tool.

        criteria options:
          - 'underperforming': has metrics, engagement_rate below the global avg
          - 'recent_drafts':   draft / refined status, created in last 7 days
          - 'old_drafts':      draft status, created > 14 days ago, never finalized
        """
        session = self._get_session()
        try:
            criteria = (criteria or "underperforming").lower()
            now = datetime.now()
            results: list[dict[str, Any]] = []

            if criteria == "underperforming":
                contents = session.query(Content).all()
                metric_rows = session.query(ContentMetrics).all()
                metrics_by_content = self._latest_metrics_by_content(metric_rows)
                if not metrics_by_content:
                    return []
                rates: list[tuple[Content, ContentMetrics, float]] = []
                for c in contents:
                    metrics_row = metrics_by_content.get(c.id)
                    if metrics_row is None or not metrics_row.views:
                        continue
                    rate = (
                        (metrics_row.likes or 0) + (metrics_row.comments or 0) + (metrics_row.shares or 0)
                    ) / metrics_row.views
                    rates.append((c, metrics_row, rate))
                if not rates:
                    return []
                avg_rate = sum(r for _, _, r in rates) / len(rates)
                weak = [(c, m, r) for c, m, r in rates if r < avg_rate]
                weak.sort(key=lambda x: x[2])
                for c, m, r in weak[:limit]:
                    results.append(
                        {
                            "id": c.id,
                            "title": c.title,
                            "content_type": c.content_type,
                            "style": c.style,
                            "status": c.status,
                            "views": m.views or 0,
                            "engagement_rate": round(r, 4),
                            "global_avg_rate": round(avg_rate, 4),
                            "reason": f"engagement {round(r, 4)} < cohort avg {round(avg_rate, 4)}",
                        }
                    )
            elif criteria == "recent_drafts":
                cutoff = now - timedelta(days=7)
                rows = (
                    session.query(Content)
                    .filter(
                        Content.status.in_(["draft", "refined"]),
                        Content.created_at >= cutoff,
                    )
                    .order_by(Content.created_at.desc())
                    .limit(limit)
                    .all()
                )
                for c in rows:
                    age_days = max(0, (now - c.created_at).days) if c.created_at else 0
                    results.append(
                        {
                            "id": c.id,
                            "title": c.title,
                            "content_type": c.content_type,
                            "style": c.style,
                            "status": c.status,
                            "age_days": age_days,
                            "reason": f"recent {c.status}, {age_days}d old, not yet finalized",
                        }
                    )
            elif criteria == "old_drafts":
                cutoff = now - timedelta(days=14)
                rows = (
                    session.query(Content)
                    .filter(Content.status == "draft", Content.created_at <= cutoff)
                    .order_by(Content.created_at)
                    .limit(limit)
                    .all()
                )
                for c in rows:
                    age_days = max(0, (now - c.created_at).days) if c.created_at else 0
                    results.append(
                        {
                            "id": c.id,
                            "title": c.title,
                            "content_type": c.content_type,
                            "style": c.style,
                            "status": c.status,
                            "age_days": age_days,
                            "reason": f"draft sitting {age_days}d, may need a decision",
                        }
                    )
            return results
        finally:
            session.close()

    def list_content_metrics(self, content_id: int) -> list[dict[str, Any]] | None:
        """Recorded numbers per platform, or None when the content is not in this workspace."""
        session = self._get_session()
        try:
            if session.query(Content.id).filter(Content.id == content_id).first() is None:
                return None
            rows = (
                session.query(ContentMetrics)
                .filter(ContentMetrics.content_id == content_id)
                .order_by(ContentMetrics.platform, ContentMetrics.recorded_at.desc(), ContentMetrics.id.desc())
                .all()
            )
            latest: dict[str | None, ContentMetrics] = {}
            for row in rows:
                latest.setdefault(row.platform, row)
            return [self._content_metrics_to_dict(row) for row in latest.values()]
        finally:
            session.close()

    def record_content_metrics(
        self,
        content_id: int,
        platform: str,
        *,
        views: int,
        likes: int,
        comments: int,
        shares: int,
    ) -> dict[str, Any] | None:
        """Set one platform's current numbers; None when the content is not in this workspace.

        Platforms report running totals, so a new reading replaces the previous
        one rather than adding a row. The analytics above keep the highest-view
        row per content, which would otherwise let a stale reading outrank a
        downward correction.
        """
        platform = platform.strip().lower()
        session = self._get_session()
        try:
            # Locking the content row serializes writers for this content: there is
            # no unique (content_id, platform) constraint to catch a racing insert.
            if session.query(Content.id).filter(Content.id == content_id).with_for_update().first() is None:
                return None
            rows = (
                session.query(ContentMetrics)
                .filter(ContentMetrics.content_id == content_id, ContentMetrics.platform == platform)
                .order_by(ContentMetrics.recorded_at.desc(), ContentMetrics.id.desc())
                .all()
            )
            if rows:
                row = rows[0]
                for stale in rows[1:]:
                    session.delete(stale)
            else:
                row = ContentMetrics(content_id=content_id, platform=platform)
                session.add(row)
            row.views = views
            row.likes = likes
            row.comments = comments
            row.shares = shares
            row.recorded_at = datetime.now()
            session.commit()
            return self._content_metrics_to_dict(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _content_metrics_to_dict(row: ContentMetrics) -> dict[str, Any]:
        views = row.views or 0
        interactions = (row.likes or 0) + (row.comments or 0) + (row.shares or 0)
        return {
            "id": row.id,
            "content_id": row.content_id,
            "platform": row.platform,
            "views": views,
            "likes": row.likes or 0,
            "comments": row.comments or 0,
            "shares": row.shares or 0,
            "engagement_rate": round(interactions / views, 4) if views else 0.0,
            "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
        }

    def archive_content(self, content_id: int) -> bool:
        session = self._get_session()
        try:
            content = session.query(Content).filter(Content.id == content_id).with_for_update().first()
            if not content:
                return False
            content.status = "archived"
            content.updated_at = datetime.now()
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_content(self, content_id: int) -> dict[str, Any] | None:
        session = self._get_session()
        try:
            # Uploads lock the same parent before checking limits and inserting.
            # Enumerate children only after acquiring it so deletion cannot miss
            # an upload that commits while the parent is being removed.
            content = session.query(Content).filter(Content.id == content_id).with_for_update().first()
            if not content:
                return None

            media_assets = (
                session.query(MediaAsset)
                .filter(MediaAsset.content_id == content_id)
                .order_by(MediaAsset.created_at)
                .all()
            )
            deleted = {
                "content": self._content_to_dict(content),
                "media_assets": [self._media_asset_to_dict(asset) for asset in media_assets],
            }

            session.query(Content).filter(Content.parent_id == content_id).update(
                {Content.parent_id: None},
                synchronize_session=False,
            )
            session.query(CalendarEvent).filter(CalendarEvent.content_id == content_id).delete(
                synchronize_session=False
            )
            session.query(ContentMetrics).filter(ContentMetrics.content_id == content_id).delete(
                synchronize_session=False
            )
            session.query(MediaAsset).filter(MediaAsset.content_id == content_id).delete(synchronize_session=False)
            session.query(PlatformPublication).filter(PlatformPublication.content_id == content_id).delete(
                synchronize_session=False
            )
            session.delete(content)
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _content_to_dict(content: Content) -> dict[str, Any]:
        return {
            "id": content.id,
            "title": content.title,
            "content": content.content,
            "content_type": content.content_type,
            "style": content.style,
            "keywords": json.loads(content.keywords) if content.keywords else [],
            "tags": json.loads(content.tags) if content.tags else [],
            "status": content.status,
            "version": content.version,
            "parent_id": content.parent_id,
            "created_at": content.created_at.isoformat() if content.created_at else None,
            "updated_at": content.updated_at.isoformat() if content.updated_at else None,
        }
