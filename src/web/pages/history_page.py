"""历史记录页面"""
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.storage import ContentStore


def render():
    """渲染历史记录页面"""
    st.markdown('<p class="sub-header">📚 历史记录</p>', unsafe_allow_html=True)
    st.markdown("查看和管理所有生成的内容。")

    st.markdown("---")

    # 筛选条件
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        filter_status = st.selectbox(
            "状态",
            options=["全部", "draft", "refined", "published", "archived"],
            format_func=lambda x: {"全部": "全部", "draft": "草稿", "refined": "已打磨", "published": "已发布", "archived": "已归档"}.get(x, x)
        )

    with col2:
        filter_type = st.selectbox(
            "类型",
            options=["全部", "xiaohongshu", "weibo", "blog", "video_script", "twitter"],
            format_func=lambda x: {"全部": "全部", "xiaohongshu": "小红书", "weibo": "微博", "blog": "博客", "video_script": "视频脚本", "twitter": "Twitter"}.get(x, x)
        )

    with col3:
        search_keyword = st.text_input("搜索", placeholder="关键词搜索")

    with col4:
        limit = st.select_slider("显示数量", options=[10, 20, 50, 100], value=20)

    # 加载数据
    try:
        store = ContentStore()
        status_filter = None if filter_status == "全部" else filter_status
        type_filter = None if filter_type == "全部" else filter_type

        contents = store.list_contents(
            status=status_filter,
            content_type=type_filter,
            limit=limit
        )

        # 搜索过滤
        if search_keyword:
            contents = [
                c for c in contents
                if search_keyword.lower() in c.get('title', '').lower()
                or search_keyword.lower() in c.get('content', '').lower()
            ]

        if contents:
            st.markdown(f"### 共 {len(contents)} 条内容")

            # 内容列表
            for item in contents:
                with st.container():
                    col1, col2 = st.columns([4, 1])

                    with col1:
                        # 标题和预览
                        title = item.get('title', '(无标题)')[:50]
                        st.markdown(f"**{title}**")
                        st.caption(f"ID: {item['id']} | 类型: {item['content_type']} | 状态: {item['status']}")

                        # 内容预览
                        with st.expander("查看内容"):
                            # 获取完整内容
                            full_content = store.get_content(item['id'])
                            if full_content:
                                if full_content.get('title'):
                                    st.markdown(f"**标题**: {full_content['title']}")
                                st.markdown(full_content['content'])

                                if full_content.get('tags'):
                                    tags_str = " ".join([f"`{t}`" for t in full_content['tags']])
                                    st.markdown(f"**标签**: {tags_str}")

                    with col2:
                        # 操作按钮
                        if st.button("✨ 打磨", key=f"refine_{item['id']}"):
                            st.session_state.content_id = item['id']
                            st.session_state.edit_content = store.get_content(item['id'])
                            st.info("请前往「内容打磨」页面")

                        if st.button("📅 加日历", key=f"calendar_{item['id']}"):
                            st.session_state.content_id = item['id']
                            st.info("请前往「发布日历」页面")

                        # 导出
                        if st.button("📋 复制", key=f"copy_{item['id']}"):
                            full_content = store.get_content(item['id'])
                            if full_content:
                                st.code(full_content['content'], language=None)

                    st.markdown("---")

            # 导出功能
            st.markdown("### 📤 导出")
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("导出 CSV"):
                    df = pd.DataFrame(contents)
                    csv = df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        "下载 CSV",
                        csv,
                        file_name=f"contents_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )

            with col2:
                if st.button("导出 JSON"):
                    import json
                    json_str = json.dumps(contents, ensure_ascii=False, indent=2)
                    st.download_button(
                        "下载 JSON",
                        json_str,
                        file_name=f"contents_{datetime.now().strftime('%Y%m%d')}.json",
                        mime="application/json"
                    )

            with col3:
                if st.button("导出 Markdown"):
                    md_content = ""
                    for item in contents:
                        full_content = store.get_content(item['id'])
                        if full_content:
                            md_content += f"## {full_content.get('title', '(无标题)')}\n\n"
                            md_content += f"类型: {full_content['content_type']} | 状态: {full_content['status']}\n\n"
                            md_content += full_content['content'] + "\n\n---\n\n"

                    st.download_button(
                        "下载 Markdown",
                        md_content,
                        file_name=f"contents_{datetime.now().strftime('%Y%m%d')}.md",
                        mime="text/markdown"
                    )

        else:
            st.info("📭 暂无内容记录")

    except Exception as e:
        st.error(f"❌ 加载失败: {str(e)}")

    # 底部提示
    st.markdown("---")
    with st.expander("💡 使用提示"):
        st.markdown("""
        - **筛选**: 按状态、类型筛选内容
        - **搜索**: 在标题和内容中搜索关键词
        - **导出**: 支持 CSV、JSON、Markdown 格式导出
        """)
