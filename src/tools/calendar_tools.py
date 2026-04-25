"""内容日历管理工具"""
from datetime import date, timedelta
from langchain_core.tools import tool

from src.storage import ContentStore
from src.models import ContentRequest, ContentType, ContentStyle
from src.tools.content_generator import ContentGenerator


def get_store() -> ContentStore:
    return ContentStore()


@tool
def add_to_calendar(content_id: int, publish_date: str, platform: str) -> str:
    """将内容加入发布日历"""
    try:
        store = get_store()
        content = store.get_content(content_id)
        if not content:
            return f"❌ 找不到 ID 为 {content_id} 的内容"

        from datetime import datetime
        try:
            scheduled_date = datetime.strptime(publish_date, "%Y-%m-%d").date()
        except ValueError:
            return f"❌ 日期格式错误，请使用 YYYY-MM-DD 格式"

        event_id = store.save_calendar_event(content_id, platform, scheduled_date)

        return f"✅ 已加入发布日历！\n\n📅 发布计划：\n- 内容 ID: {content_id}\n- 平台: {platform}\n- 日期: {publish_date}\n- 事件 ID: {event_id}"

    except Exception as e:
        return f"❌ 添加失败: {str(e)}"


@tool
def view_calendar(days: int = 7) -> str:
    """查看内容日历"""
    try:
        store = get_store()
        start_date = date.today()
        end_date = start_date + timedelta(days=days)
        events = store.get_calendar_events(start_date, end_date)

        if not events:
            return f"📅 未来 {days} 天没有发布计划"

        events_by_date = {}
        for event in events:
            event_date = event['scheduled_date']
            if event_date not in events_by_date:
                events_by_date[event_date] = []
            events_by_date[event_date].append(event)

        output = f"📅 未来 {days} 天的发布日历：\n\n"
        for event_date in sorted(events_by_date.keys()):
            output += f"📆 {event_date}\n"
            for event in events_by_date[event_date]:
                output += f"  • [{event['platform']}] {event['content_title'] or '(无标题)'} (ID: {event['content_id']})\n"
                output += f"    状态: {event['status']}\n"
            output += "\n"
        return output

    except Exception as e:
        return f"❌ 查询失败: {str(e)}"


@tool
def batch_generate_week(topic: str, content_type: str, style: str = "casual") -> str:
    """批量生成一周内容"""
    try:
        content_type_enum = ContentType(content_type)
        style_enum = ContentStyle(style)
        generator = ContentGenerator()
        store = get_store()

        results = []
        for day in range(7):
            day_topic = f"{topic} - 第{day+1}天"
            request = ContentRequest(topic=day_topic, content_type=content_type_enum, style=style_enum, length="medium")
            result = generator.generate(request)
            content_id = store.save_content(
                result,
                llm_provider=generator.provider,
                model_name=generator.model,
                style=style_enum.value,
            )

            publish_date = date.today() + timedelta(days=day)
            store.save_calendar_event(content_id, content_type, publish_date)
            results.append({"day": day + 1, "content_id": content_id, "title": result.title, "date": publish_date.isoformat()})

        output = f"✅ 批量生成成功！已生成 7 天的{content_type}内容：\n\n"
        for r in results:
            output += f"📅 第{r['day']}天 ({r['date']})\n   ID: {r['content_id']}\n"
            if r['title']:
                output += f"   标题: {r['title']}\n"
            output += "\n"
        output += "💡 提示：使用 view_calendar 查看完整日历"
        return output

    except Exception as e:
        return f"❌ 批量生成失败: {str(e)}"


@tool
def get_content_stats() -> str:
    """查看内容统计"""
    try:
        store = get_store()
        stats = store.get_content_stats()

        output = "📊 内容统计：\n\n"
        output += f"📝 总内容数: {stats['total_contents']}\n\n"

        if stats['by_type']:
            output += "按类型分布：\n"
            for ct, count in stats['by_type'].items():
                output += f"  • {ct}: {count}\n"
            output += "\n"

        if stats['by_status']:
            output += "按状态分布：\n"
            for st, count in stats['by_status'].items():
                output += f"  • {st}: {count}\n"
        return output

    except Exception as e:
        return f"❌ 查询失败: {str(e)}"
