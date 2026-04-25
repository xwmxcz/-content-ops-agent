"""Content Ops Agent - Streamlit Web UI"""
import streamlit as st
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 页面配置
st.set_page_config(
    page_title="Content Ops Agent",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/your-repo/content-ops-agent',
        'Report a bug': "https://github.com/your-repo/content-ops-agent/issues",
    }
)

# 自定义样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E88E5;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #424242;
        margin-bottom: 0.5rem;
    }
    .content-card {
        background-color: #f5f5f5;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .stButton>button {
        width: 100%;
    }
    div[data-testid="stSidebarNav"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# 侧边栏导航
with st.sidebar:
    st.markdown("### 📝 Content Ops Agent")
    st.markdown("---")

    # 导航菜单
    page = st.radio(
        "导航",
        ["🏠 首页", "📝 内容生成", "✨ 内容打磨", "📅 发布日历", "📚 历史记录", "📊 统计分析"],
        label_visibility="collapsed"
    )

    st.markdown("---")

    # 配置信息
    with st.expander("⚙️ 配置"):
        from src.utils import config
        st.text(f"LLM: {config.LLM_PROVIDER}")
        st.text(f"Model: {config.get_model()}")

    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #888; font-size: 0.8rem;">
        Phase 2 - Streamlit Web UI<br>
        v0.2.0
    </div>
    """, unsafe_allow_html=True)

# 页面路由
if page == "🏠 首页":
    st.markdown('<p class="main-header">欢迎使用 Content Ops Agent</p>', unsafe_allow_html=True)
    st.markdown("智能内容运营助手，帮你高效创作、优化和管理内容。")

    st.markdown("---")

    # 快速入口
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 📝 内容生成")
        st.markdown("生成小红书、微博、博客、视频脚本等多种类型内容")
        if st.button("开始生成", key="btn_generate"):
            st.session_state.page = "📝 内容生成"
            st.rerun()

    with col2:
        st.markdown("### ✨ 内容打磨")
        st.markdown("改写、风格切换、标题优化、SEO 分析")
        if st.button("开始打磨", key="btn_refine"):
            st.session_state.page = "✨ 内容打磨"
            st.rerun()

    with col3:
        st.markdown("### 📅 发布日历")
        st.markdown("管理内容发布计划，批量生成一周内容")
        if st.button("查看日历", key="btn_calendar"):
            st.session_state.page = "📅 发布日历"
            st.rerun()

    st.markdown("---")

    # 最近内容
    st.markdown("### 📚 最近内容")
    try:
        from src.storage import ContentStore
        store = ContentStore()
        recent = store.list_contents(limit=5)

        if recent:
            for item in recent:
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.markdown(f"**{item.get('title', '(无标题)')[:50]}**")
                        st.caption(f"ID: {item['id']} | {item['content_type']}")
                    with col2:
                        st.caption(f"状态: {item['status']}")
                    with col3:
                        st.caption(item.get('created_at', '')[:10] if item.get('created_at') else '')
        else:
            st.info("暂无内容，开始创作吧！")
    except Exception as e:
        st.warning(f"无法加载内容: {e}")

elif page == "📝 内容生成":
    # 导入生成页面
    from src.web.pages import generate_page
    generate_page.render()

elif page == "✨ 内容打磨":
    from src.web.pages import refine_page
    refine_page.render()

elif page == "📅 发布日历":
    from src.web.pages import calendar_page
    calendar_page.render()

elif page == "📚 历史记录":
    from src.web.pages import history_page
    history_page.render()

elif page == "📊 统计分析":
    from src.web.pages import stats_page
    stats_page.render()
