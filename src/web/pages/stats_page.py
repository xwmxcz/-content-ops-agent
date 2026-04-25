"""统计分析页面"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.storage import ContentStore


def render():
    """渲染统计分析页面"""
    st.markdown('<p class="sub-header">📊 统计分析</p>', unsafe_allow_html=True)
    st.markdown("内容创作数据统计和分析。")

    st.markdown("---")

    try:
        store = ContentStore()

        # 基础统计
        stats = store.get_content_stats()

        # 核心指标
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📝 总内容数", stats['total_contents'])
        with col2:
            draft_count = stats['by_status'].get('draft', 0)
            st.metric("📝 草稿", draft_count)
        with col3:
            refined_count = stats['by_status'].get('refined', 0)
            st.metric("✨ 已打磨", refined_count)
        with col4:
            published_count = stats['by_status'].get('published', 0)
            st.metric("📅 已发布", published_count)

        st.markdown("---")

        # 图表区域
        col_left, col_right = st.columns(2)

        with col_left:
            # 按类型分布
            st.markdown("### 📊 内容类型分布")
            if stats['by_type']:
                type_df = pd.DataFrame(
                    list(stats['by_type'].items()),
                    columns=['类型', '数量']
                )
                type_df['类型'] = type_df['类型'].map({
                    'xiaohongshu': '小红书',
                    'weibo': '微博',
                    'blog': '博客',
                    'video_script': '视频脚本',
                    'twitter': 'Twitter'
                })

                fig = px.pie(type_df, values='数量', names='类型', hole=0.4)
                fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("暂无数据")

        with col_right:
            # 按状态分布
            st.markdown("### 📊 内容状态分布")
            if stats['by_status']:
                status_df = pd.DataFrame(
                    list(stats['by_status'].items()),
                    columns=['状态', '数量']
                )
                status_df['状态'] = status_df['状态'].map({
                    'draft': '草稿',
                    'refined': '已打磨',
                    'published': '已发布',
                    'archived': '已归档'
                })

                fig = px.bar(status_df, x='状态', y='数量', color='状态')
                fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("暂无数据")

        st.markdown("---")

        # 日历统计
        st.markdown("### 📅 发布日历统计")

        # 获取未来 30 天的日历事件
        start_date = date.today()
        end_date = start_date + timedelta(days=30)
        events = store.get_calendar_events(start_date, end_date)

        if events:
            events_df = pd.DataFrame(events)
            events_df['scheduled_date'] = pd.to_datetime(events_df['scheduled_date'])

            # 按日期统计
            daily_counts = events_df.groupby('scheduled_date').size().reset_index(name='count')

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=daily_counts['scheduled_date'],
                y=daily_counts['count'],
                mode='lines+markers',
                name='发布计划',
                line=dict(color='#1E88E5', width=2),
                marker=dict(size=8)
            ))
            fig.update_layout(
                title='未来 30 天发布计划趋势',
                xaxis_title='日期',
                yaxis_title='计划数量',
                height=300,
                margin=dict(t=40, b=20, l=20, r=20)
            )
            st.plotly_chart(fig, use_container_width=True)

            # 按平台统计
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**按平台分布**")
                platform_counts = events_df['platform'].value_counts()
                st.dataframe(platform_counts, use_container_width=True)

            with col2:
                st.markdown("**按状态分布**")
                status_counts = events_df['status'].value_counts()
                st.dataframe(status_counts, use_container_width=True)

        else:
            st.info("未来 30 天暂无发布计划")

        st.markdown("---")

        # 详细数据表
        st.markdown("### 📋 详细数据")

        # 最近内容表
        recent = store.list_contents(limit=50)
        if recent:
            df = pd.DataFrame(recent)
            df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
            df = df[['id', 'title', 'content_type', 'status', 'created_at']]
            df.columns = ['ID', '标题', '类型', '状态', '创建时间']

            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无数据")

    except Exception as e:
        st.error(f"❌ 加载失败: {str(e)}")

    # 底部提示
    st.markdown("---")
    with st.expander("💡 指标说明"):
        st.markdown("""
        - **总内容数**: 数据库中所有内容的数量
        - **草稿**: 新生成但未打磨的内容
        - **已打磨**: 经过改写或风格切换的内容
        - **已发布**: 已添加到发布日历的内容
        - **类型分布**: 各平台内容的占比
        """)
