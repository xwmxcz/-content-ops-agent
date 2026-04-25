"""发布日历页面"""
import streamlit as st
from datetime import date, timedelta, datetime
import pandas as pd
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.storage import ContentStore
from src.models import ContentRequest, ContentType, ContentStyle
from src.tools.content_generator import ContentGenerator


def render():
    """渲染发布日历页面"""
    st.markdown('<p class="sub-header">📅 发布日历</p>', unsafe_allow_html=True)
    st.markdown("管理内容发布计划，批量生成一周内容。")

    st.markdown("---")

    # 标签页
    tab1, tab2, tab3 = st.tabs(["📋 日历视图", "➕ 添加计划", "⚡ 批量生成"])

    with tab1:
        st.markdown("### 📅 发布计划")

        # 日期范围选择
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("开始日期", value=date.today())
        with col2:
            days = st.select_slider("显示天数", options=[7, 14, 30], value=7)

        end_date = start_date + timedelta(days=days)

        # 加载日历事件
        try:
            store = ContentStore()
            events = store.get_calendar_events(start_date, end_date)

            if events:
                # 按日期分组
                events_df = pd.DataFrame(events)
                events_df['scheduled_date'] = pd.to_datetime(events_df['scheduled_date'])
                events_df = events_df.sort_values('scheduled_date')

                # 日历视图
                for event_date in events_df['scheduled_date'].unique():
                    day_events = events_df[events_df['scheduled_date'] == event_date]
                    date_str = pd.Timestamp(event_date).strftime('%Y-%m-%d (%A)')

                    with st.container():
                        st.markdown(f"#### 📆 {date_str}")

                        for _, event in day_events.iterrows():
                            col1, col2, col3 = st.columns([3, 2, 1])
                            with col1:
                                st.markdown(f"**{event['content_title'] or '(无标题)'}**")
                                st.caption(f"内容 ID: {event['content_id']}")
                            with col2:
                                st.markdown(f"平台: `{event['platform']}`")
                            with col3:
                                status_color = {"planned": "🔵", "published": "🟢", "cancelled": "🔴"}.get(event['status'], "⚪")
                                st.markdown(f"{status_color} {event['status']}")

                        st.markdown("---")

                # 统计信息
                st.markdown("### 📊 计划统计")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("总计划数", len(events))
                with col2:
                    by_platform = events_df['platform'].value_counts().to_dict()
                    st.metric("平台数", len(by_platform))
                with col3:
                    by_status = events_df['status'].value_counts().to_dict()
                    st.metric("已发布", by_status.get("published", 0))

            else:
                st.info(f"📅 {start_date} 至 {end_date} 期间没有发布计划")

        except Exception as e:
            st.error(f"❌ 加载失败: {str(e)}")

    with tab2:
        st.markdown("### ➕ 添加发布计划")

        col1, col2 = st.columns(2)

        with col1:
            # 选择内容
            plan_content_id = st.number_input("内容 ID", min_value=1, step=1)

            # 快速选择最近内容
            with st.expander("📚 从最近内容选择"):
                try:
                    store = ContentStore()
                    recent = store.list_contents(limit=10)
                    for item in recent:
                        if st.button(
                            f"{item['id']}: {item.get('title', '(无标题)')[:30]}",
                            key=f"plan_{item['id']}"
                        ):
                            plan_content_id = item['id']
                            st.rerun()
                except Exception as e:
                    st.warning(f"无法加载: {e}")

        with col2:
            # 发布配置
            plan_date = st.date_input("发布日期", value=date.today() + timedelta(days=1))
            plan_platform = st.selectbox(
                "发布平台",
                options=["xiaohongshu", "weibo", "blog", "twitter"],
                format_func=lambda x: {"xiaohongshu": "小红书", "weibo": "微博", "blog": "博客", "twitter": "Twitter"}[x]
            )

        if st.button("📅 添加到日历", type="primary"):
            try:
                store = ContentStore()
                content = store.get_content(plan_content_id)

                if content:
                    event_id = store.save_calendar_event(
                        plan_content_id,
                        plan_platform,
                        plan_date
                    )
                    st.success(f"✅ 已添加到日历！事件 ID: {event_id}")
                else:
                    st.error(f"❌ 找不到 ID 为 {plan_content_id} 的内容")

            except Exception as e:
                st.error(f"❌ 添加失败: {str(e)}")

    with tab3:
        st.markdown("### ⚡ 批量生成一周内容")

        col1, col2 = st.columns(2)

        with col1:
            batch_topic = st.text_input(
                "主题",
                placeholder="例如：职场效率提升"
            )
            batch_platform = st.selectbox(
                "内容类型",
                options=["xiaohongshu", "weibo", "blog"],
                format_func=lambda x: {"xiaohongshu": "小红书", "weibo": "微博", "blog": "博客"}[x],
                key="batch_platform"
            )

        with col2:
            batch_style = st.selectbox(
                "内容风格",
                options=[
                    ("轻松活泼", "casual"),
                    ("专业严谨", "professional"),
                    ("营销推广", "marketing")
                ],
                format_func=lambda x: x[0],
                key="batch_style"
            )

        st.markdown("---")

        if st.button("🚀 开始批量生成", type="primary"):
            if batch_topic:
                progress_bar = st.progress(0)
                status_text = st.empty()

                try:
                    generator = ContentGenerator()
                    store = ContentStore()

                    results = []
                    for day in range(7):
                        status_text.text(f"正在生成第 {day + 1}/7 天内容...")
                        progress_bar.progress((day + 1) / 7)

                        day_topic = f"{batch_topic} - 第{day+1}天"
                        request = ContentRequest(
                            topic=day_topic,
                            content_type=ContentType(batch_platform),
                            style=ContentStyle(batch_style[1]),
                            length="medium"
                        )

                        result = generator.generate(request)
                        content_id = store.save_content(
                            result,
                            llm_provider=generator.provider,
                            model_name=generator.model,
                            style=batch_style[1],
                        )

                        publish_date = date.today() + timedelta(days=day)
                        store.save_calendar_event(content_id, batch_platform, publish_date)

                        results.append({
                            "day": day + 1,
                            "content_id": content_id,
                            "title": result.title,
                            "date": publish_date.isoformat()
                        })

                    st.success("✅ 批量生成完成！")

                    # 显示结果
                    st.markdown("### 📅 生成结果")
                    for r in results:
                        st.markdown(f"- **第{r['day']}天** ({r['date']}): ID {r['content_id']} - {r.get('title', '(无标题)')}")

                except Exception as e:
                    st.error(f"❌ 生成失败: {str(e)}")

            else:
                st.warning("请输入主题")

    # 底部提示
    st.markdown("---")
    with st.expander("💡 使用提示"):
        st.markdown("""
        - **日历视图**: 查看未来发布计划，支持 7/14/30 天视图
        - **添加计划**: 将已有内容添加到发布日历
        - **批量生成**: 一键生成一周的内容并自动添加到日历
        """)
