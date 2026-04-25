"""内容打磨页面"""
import streamlit as st
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.storage import ContentStore
from src.tools.content_generator import ContentGenerator
from src.models import ContentStyle, GeneratedContent, ContentType
from src.utils import config
from datetime import datetime

# 模型配置（与生成页面保持一致）
PROVIDER_MODELS = {
    "siliconflow": {
        "name": "硅基流动",
        "models": [
            ("Qwen/Qwen2.5-7B-Instruct", "Qwen2.5-7B (快速)"),
            ("Qwen/Qwen2.5-14B-Instruct", "Qwen2.5-14B (推荐)"),
            ("Qwen/Qwen2.5-32B-Instruct", "Qwen2.5-32B (高质量)"),
            ("Qwen/Qwen2.5-72B-Instruct", "Qwen2.5-72B (最强)"),
        ],
        "api_key_env": "SILICONFLOW_API_KEY"
    },
    "deepseek": {
        "name": "DeepSeek",
        "models": [
            ("deepseek-chat", "DeepSeek Chat (推荐)"),
            ("deepseek-coder", "DeepSeek Coder"),
        ],
        "api_key_env": "DEEPSEEK_API_KEY"
    },
    "moonshot": {
        "name": "Moonshot",
        "models": [
            ("moonshot-v1-8k", "Moonshot V1 8K"),
            ("moonshot-v1-32k", "Moonshot V1 32K"),
        ],
        "api_key_env": "MOONSHOT_API_KEY"
    },
    "claude": {
        "name": "Claude",
        "models": [
            ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet (推荐)"),
            ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku (快速)"),
        ],
        "api_key_env": "ANTHROPIC_API_KEY"
    }
}

TOKEN_OPTIONS = {
    "中等 (1024)": 1024,
    "长篇 (2048)": 2048,
    "超长 (4096)": 4096,
    "极长 (8192)": 8192,
}


def render():
    """渲染内容打磨页面"""
    st.markdown('<p class="sub-header">✨ 内容打磨</p>', unsafe_allow_html=True)
    st.markdown("改写、风格切换、标题优化、SEO 分析，让内容更出彩。")

    st.markdown("---")

    # 选择内容
    col_select, col_content = st.columns([1, 2])

    with col_select:
        st.markdown("### 📄 选择内容")

        # 内容 ID 输入
        content_id = st.number_input(
            "内容 ID",
            min_value=1,
            value=st.session_state.get("content_id", 1),
            step=1
        )

        # 加载内容
        if st.button("加载内容", type="primary"):
            try:
                store = ContentStore()
                content = store.get_content(content_id)
                if content:
                    st.session_state.edit_content = content
                    st.success(f"✅ 已加载内容 ID: {content_id}")
                else:
                    st.error(f"❌ 找不到 ID 为 {content_id} 的内容")
            except Exception as e:
                st.error(f"❌ 加载失败: {str(e)}")

        # 显示最近内容列表
        with st.expander("📚 最近内容"):
            try:
                store = ContentStore()
                recent = store.list_contents(limit=10)
                for item in recent:
                    if st.button(
                        f"{item['id']}: {item.get('title', '(无标题)')[:25]}",
                        key=f"select_{item['id']}"
                    ):
                        st.session_state.content_id = item['id']
                        st.session_state.edit_content = store.get_content(item['id'])
                        st.rerun()
            except Exception as e:
                st.warning(f"无法加载: {e}")

        # 模型配置
        st.markdown("---")
        st.markdown("### 🤖 模型设置")

        available_providers = []
        for p in PROVIDER_MODELS.keys():
            key_env = PROVIDER_MODELS[p]["api_key_env"]
            if getattr(config, key_env, None):
                available_providers.append(p)

        selected_provider = st.selectbox(
            "LLM 提供商",
            options=available_providers,
            format_func=lambda x: PROVIDER_MODELS[x]["name"],
            key="refine_provider"
        )

        models = PROVIDER_MODELS[selected_provider]["models"]
        selected_model = st.selectbox(
            "模型",
            options=[m[0] for m in models],
            format_func=lambda x: next((m[1] for m in models if m[0] == x), x),
            key="refine_model"
        )

        max_tokens_label = st.select_slider(
            "输出长度",
            options=list(TOKEN_OPTIONS.keys()),
            value="长篇 (2048)",
            key="refine_tokens"
        )
        max_tokens = TOKEN_OPTIONS[max_tokens_label]

    with col_content:
        st.markdown("### 📝 内容预览")

        content = st.session_state.get("edit_content")
        if content:
            # 显示标题
            if content.get("title"):
                st.markdown(f"**标题**: {content['title']}")

            # 显示正文
            st.markdown("**正文**:")
            st.text_area(
                "内容",
                value=content["content"],
                height=250,
                key="content_preview",
                disabled=True
            )

            # 显示元信息
            col1, col2, col3 = st.columns(3)
            with col1:
                st.caption(f"类型: {content.get('content_type', '-')}")
            with col2:
                st.caption(f"风格: {content.get('style', '-')}")
            with col3:
                st.caption(f"状态: {content.get('status', '-')}")

            st.markdown("---")

            # 打磨操作
            st.markdown("### ✨ 打磨操作")

            tab1, tab2, tab3, tab4 = st.tabs(["改写", "风格切换", "标题优化", "SEO 分析"])

            with tab1:
                st.markdown("**按指令改写**")
                instruction = st.text_area(
                    "改写指令",
                    placeholder="例如：让语气更亲切，增加一些表情符号，扩展内容到800字以上",
                    height=80
                )
                if st.button("🔄 执行改写", type="primary"):
                    if instruction:
                        with st.spinner(f"正在改写... (模型: {selected_model})"):
                            try:
                                generator = ContentGenerator(
                                    provider=selected_provider,
                                    model=selected_model
                                )
                                system_prompt = "你是一位专业的内容编辑，擅长根据指令改写内容。请保持内容的核心信息，按照用户的指令进行改写。"
                                user_prompt = f"""请根据以下指令改写内容：

指令：{instruction}

原内容：
{content['content']}

请直接输出改写后的内容。"""

                                refined_text = generator.client.generate(
                                    system_prompt,
                                    user_prompt,
                                    temperature=0.7,
                                    max_tokens=max_tokens
                                )

                                # 保存新版本
                                refined = GeneratedContent(
                                    content=refined_text,
                                    title=content.get("title"),
                                    tags=content.get("tags"),
                                    content_type=ContentType(content["content_type"]),
                                    created_at=datetime.now()
                                )

                                store = ContentStore()
                                new_id = store.save_content(
                                    refined,
                                    llm_provider=generator.provider,
                                    model_name=generator.model,
                                    parent_id=content_id,
                                    style=content.get("style", "casual"),
                                    keywords=content.get("keywords", []),
                                )
                                store.update_content(new_id, status="refined")

                                st.success(f"✅ 改写完成！新内容 ID: {new_id}")
                                st.markdown("### 改写结果")
                                st.markdown(refined_text)
                                st.caption(f"字数: {len(refined_text)} 字")

                                # 更新 session
                                st.session_state.edit_content = store.get_content(new_id)
                                st.session_state.content_id = new_id

                            except Exception as e:
                                st.error(f"❌ 改写失败: {str(e)}")
                    else:
                        st.warning("请输入改写指令")

            with tab2:
                st.markdown("**切换风格**")
                new_style = st.selectbox(
                    "选择新风格",
                    options=[
                        ("轻松活泼", "casual"),
                        ("专业严谨", "professional"),
                        ("营销推广", "marketing"),
                        ("故事叙述", "storytelling")
                    ],
                    format_func=lambda x: x[0]
                )
                if st.button("🎨 切换风格", type="primary"):
                    with st.spinner(f"正在改写... (模型: {selected_model})"):
                        try:
                            style_enum = ContentStyle(new_style[1])

                            generator = ContentGenerator(
                                provider=selected_provider,
                                model=selected_model
                            )
                            system_prompt = f"你是一位专业的内容编辑，擅长风格转换。请将内容改写为{style_enum.value}风格，保持核心信息不变。"
                            user_prompt = f"""请将以下内容改写为{style_enum.value}风格：

{content['content']}

请直接输出改写后的内容。"""

                            refined_text = generator.client.generate(
                                system_prompt,
                                user_prompt,
                                temperature=0.7,
                                max_tokens=max_tokens
                            )

                            # 保存
                            refined = GeneratedContent(
                                content=refined_text,
                                title=content.get("title"),
                                tags=content.get("tags"),
                                content_type=ContentType(content["content_type"]),
                                created_at=datetime.now()
                            )

                            store = ContentStore()
                            new_id = store.save_content(
                                refined,
                                llm_provider=generator.provider,
                                model_name=generator.model,
                                parent_id=content_id,
                                style=new_style[1],
                                keywords=content.get("keywords", []),
                            )
                            store.update_content(new_id, status="refined", style=new_style[1])

                            st.success(f"✅ 风格切换完成！新内容 ID: {new_id}")
                            st.markdown("### 改写结果")
                            st.markdown(refined_text)

                        except Exception as e:
                            st.error(f"❌ 改写失败: {str(e)}")

            with tab3:
                st.markdown("**生成标题选项**")
                title_count = st.slider("标题数量", 3, 10, 5)
                if st.button("💡 生成标题", type="primary"):
                    with st.spinner(f"正在生成... (模型: {selected_model})"):
                        try:
                            generator = ContentGenerator(
                                provider=selected_provider,
                                model=selected_model
                            )
                            system_prompt = "你是一位专业的标题创作专家，擅长创作吸引眼球、引发点击欲望的标题。"
                            user_prompt = f"""请为以下内容创作{title_count}个标题选项：

{content['content'][:500]}...

请按以下格式输出：
1. [标题1]
2. [标题2]
..."""

                            result = generator.client.generate(
                                system_prompt,
                                user_prompt,
                                temperature=0.9,
                                max_tokens=1024
                            )

                            st.markdown("### 💡 标题选项")
                            st.markdown(result)

                        except Exception as e:
                            st.error(f"❌ 生成失败: {str(e)}")

            with tab4:
                st.markdown("**SEO 分析**")
                if st.button("🔍 分析 SEO", type="primary"):
                    with st.spinner(f"正在分析... (模型: {selected_model})"):
                        try:
                            generator = ContentGenerator(
                                provider=selected_provider,
                                model=selected_model
                            )
                            system_prompt = "你是一位 SEO 专家，擅长关键词优化和内容 SEO 分析。请提供专业、可操作的优化建议。"
                            user_prompt = f"""请分析以下内容的 SEO 优化建议：

标题：{content.get('title', '无')}
正文：{content['content'][:800]}...

请提供：
1. 核心关键词建议（3-5个）
2. 标题优化建议
3. 内容结构优化建议
4. 元描述建议（150字以内）"""

                            result = generator.client.generate(
                                system_prompt,
                                user_prompt,
                                temperature=0.5,
                                max_tokens=2048
                            )

                            st.markdown("### 🔍 SEO 分析结果")
                            st.markdown(result)

                        except Exception as e:
                            st.error(f"❌ 分析失败: {str(e)}")

        else:
            st.info("请在左侧输入内容 ID 并点击「加载内容」")

    # 底部提示
    st.markdown("---")
    with st.expander("💡 打磨技巧"):
        st.markdown("""
        - **改写**: 用自然语言描述你想要的变化，如"增加一些表情"、"语气更正式"、"扩展到800字"
        - **风格切换**: 快速转换为不同风格，适合多平台分发
        - **标题优化**: 生成多个标题选项，用于 A/B 测试
        - **SEO 分析**: 获取关键词和结构优化建议

        ### 模型建议
        - 打磨建议使用 **Qwen2.5-14B** 或更高级模型，以获得更好的改写质量
        """)
