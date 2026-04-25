"""内容生成页面"""
import streamlit as st
from datetime import datetime
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.models import ContentRequest, ContentType, ContentStyle
from src.tools.content_generator import ContentGenerator
from src.storage import ContentStore
from src.utils import config

# 模型配置
PROVIDER_MODELS = {
    "siliconflow": {
        "name": "硅基流动",
        "models": [
            ("Qwen/Qwen2.5-7B-Instruct", "Qwen2.5-7B (快速)"),
            ("Qwen/Qwen2.5-14B-Instruct", "Qwen2.5-14B (推荐)"),
            ("Qwen/Qwen2.5-32B-Instruct", "Qwen2.5-32B (高质量)"),
            ("Qwen/Qwen2.5-72B-Instruct", "Qwen2.5-72B (最强)"),
            ("deepseek-ai/DeepSeek-V2.5", "DeepSeek-V2.5"),
            ("THUDM/glm-4-9b-chat", "GLM-4-9B"),
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
        "name": "Moonshot (月之暗面)",
        "models": [
            ("moonshot-v1-8k", "Moonshot V1 8K"),
            ("moonshot-v1-32k", "Moonshot V1 32K"),
            ("moonshot-v1-128k", "Moonshot V1 128K"),
        ],
        "api_key_env": "MOONSHOT_API_KEY"
    },
    "claude": {
        "name": "Claude (Anthropic)",
        "models": [
            ("claude-3-5-sonnet-20241022", "Claude 3.5 Sonnet (推荐)"),
            ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku (快速)"),
            ("claude-3-opus-20240229", "Claude 3 Opus (最强)"),
        ],
        "api_key_env": "ANTHROPIC_API_KEY"
    }
}

# Token 数量配置
TOKEN_OPTIONS = {
    "短篇 (512)": 512,
    "中等 (1024)": 1024,
    "长篇 (2048)": 2048,
    "超长 (4096)": 4096,
    "极长 (8192)": 8192,
}


def render():
    """渲染内容生成页面"""
    st.markdown('<p class="sub-header">📝 内容生成</p>', unsafe_allow_html=True)
    st.markdown("选择平台和类型，输入主题，一键生成高质量内容。")

    st.markdown("---")

    # 左侧：配置区
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.markdown("### 🎯 生成配置")

        # ===== 模型配置区域 =====
        st.markdown("#### 🤖 模型设置")

        # 提供商选择
        provider_options = list(PROVIDER_MODELS.keys())
        provider_names = [PROVIDER_MODELS[p]["name"] for p in provider_options]

        # 检查哪些提供商有 API Key
        available_providers = []
        for p in provider_options:
            key_env = PROVIDER_MODELS[p]["api_key_env"]
            if getattr(config, key_env, None):
                available_providers.append(p)

        # 默认提供商
        default_provider_idx = 0
        if config.LLM_PROVIDER in available_providers:
            default_provider_idx = available_providers.index(config.LLM_PROVIDER)

        selected_provider = st.selectbox(
            "LLM 提供商",
            options=available_providers,
            format_func=lambda x: PROVIDER_MODELS[x]["name"],
            index=default_provider_idx,
            help="选择 AI 模型提供商（需要有对应的 API Key）"
        )

        # 模型选择
        models = PROVIDER_MODELS[selected_provider]["models"]
        selected_model = st.selectbox(
            "模型",
            options=[m[0] for m in models],
            format_func=lambda x: next((m[1] for m in models if m[0] == x), x),
            help="选择要使用的模型，更大的模型质量更好但速度较慢"
        )

        # Token 数量选择
        max_tokens_label = st.select_slider(
            "输出长度",
            options=list(TOKEN_OPTIONS.keys()),
            value="长篇 (2048)",
            help="控制生成内容的最大长度"
        )
        max_tokens = TOKEN_OPTIONS[max_tokens_label]

        # Temperature 滑块
        temperature = st.slider(
            "创意度 (Temperature)",
            min_value=0.0,
            max_value=1.0,
            value=0.7,
            step=0.1,
            help="更高的值会产生更有创意但不太确定的结果"
        )

        st.markdown("---")

        # ===== 内容配置区域 =====
        st.markdown("#### 📝 内容设置")

        # 平台选择
        platform = st.selectbox(
            "目标平台",
            options=[
                ("小红书", "xiaohongshu"),
                ("微博", "weibo"),
                ("博客文章", "blog"),
                ("视频脚本", "video_script"),
                ("Twitter", "twitter")
            ],
            format_func=lambda x: x[0]
        )

        # 风格选择
        style = st.selectbox(
            "内容风格",
            options=[
                ("轻松活泼", "casual"),
                ("专业严谨", "professional"),
                ("营销推广", "marketing"),
                ("故事叙述", "storytelling")
            ],
            format_func=lambda x: x[0]
        )

        # 长度选择
        length = st.select_slider(
            "内容长度",
            options=["short", "medium", "long"],
            format_func=lambda x: {"short": "短篇", "medium": "中等", "long": "长篇"}[x],
            value="medium"
        )

        # 关键词
        keywords = st.text_input(
            "关键词（可选）",
            placeholder="多个关键词用逗号分隔，如：效率,职场,技巧"
        )

    with col_right:
        st.markdown("### 📝 输入主题")

        # 主题输入
        topic = st.text_area(
            "内容主题",
            placeholder="例如：如何提高工作效率的10个小技巧",
            height=120
        )

        # 生成按钮
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
        with col_btn1:
            generate_btn = st.button("🚀 生成内容", type="primary", use_container_width=True)
        with col_btn2:
            title_btn = st.button("💡 生成标题", use_container_width=True)

        # 显示当前配置信息
        st.caption(f"当前模型: `{PROVIDER_MODELS[selected_provider]['name']} / {selected_model}` | 最大输出: `{max_tokens}` tokens")

        st.markdown("---")

        # 结果展示区
        if generate_btn and topic:
            with st.spinner(f"正在生成内容... (模型: {selected_model})"):
                try:
                    # 创建生成器
                    generator = ContentGenerator(
                        provider=selected_provider,
                        model=selected_model
                    )

                    # 临时修改 max_tokens
                    original_max_tokens = config.MAX_TOKENS
                    original_temperature = config.TEMPERATURE

                    # 构建请求
                    keywords_list = [k.strip() for k in keywords.split(",")] if keywords else None
                    request = ContentRequest(
                        topic=topic,
                        content_type=ContentType(platform[1]),
                        style=ContentStyle(style[1]),
                        keywords=keywords_list,
                        length=length
                    )

                    # 生成内容（使用自定义参数）
                    system_prompt = generator.templates.get_system_prompt(
                        request.content_type, request.style
                    )
                    user_prompt = generator._build_user_prompt(request)

                    content_text = generator.client.generate(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )

                    result = generator._parse_response(content_text, request.content_type)

                    # 保存到数据库
                    store = ContentStore()
                    content_id = store.save_content(
                        result,
                        llm_provider=generator.provider,
                        model_name=generator.model,
                        style=style[1],
                        keywords=keywords_list,
                    )

                    # 显示结果
                    st.success(f"✅ 内容生成成功！ID: {content_id}")

                    # 显示模型信息
                    st.info(f"使用模型: {PROVIDER_MODELS[selected_provider]['name']} / {selected_model}")

                    # 标题
                    if result.title:
                        st.markdown("### 📌 标题")
                        st.markdown(f"**{result.title}**")

                    # 正文
                    st.markdown("### 📄 正文")
                    st.markdown(result.content)

                    # 字数统计
                    char_count = len(result.content)
                    st.caption(f"字数统计: {char_count} 字")

                    # 标签
                    if result.tags:
                        st.markdown("### 🏷️ 标签")
                        tag_str = " ".join([f"`{tag}`" for tag in result.tags])
                        st.markdown(tag_str)

                    # 操作按钮
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("📋 复制内容", key="copy_btn"):
                            st.code(result.content, language=None)
                            st.info("已显示内容，可手动复制")
                    with col2:
                        if st.button("✨ 去打磨", key="refine_btn"):
                            st.session_state.content_id = content_id
                            st.info(f"内容 ID: {content_id}，请前往「内容打磨」页面")
                    with col3:
                        if st.button("📅 加入日历", key="calendar_btn"):
                            st.session_state.content_id = content_id
                            st.info(f"内容 ID: {content_id}，请前往「发布日历」页面")

                    # 存储到 session state
                    st.session_state.last_content = {
                        "id": content_id,
                        "title": result.title,
                        "content": result.content,
                        "tags": result.tags,
                        "provider": selected_provider,
                        "model": selected_model
                    }

                except Exception as e:
                    st.error(f"❌ 生成失败: {str(e)}")
                    with st.expander("🔍 错误详情"):
                        st.code(str(e))

        elif title_btn and topic:
            with st.spinner("正在生成标题选项..."):
                try:
                    generator = ContentGenerator(
                        provider=selected_provider,
                        model=selected_model
                    )
                    from src.tools.content_tools import generate_title_options
                    result = generate_title_options(topic, platform[1], 5)
                    st.markdown("### 💡 标题选项")
                    st.markdown(result)
                except Exception as e:
                    st.error(f"❌ 生成失败: {str(e)}")

        elif generate_btn and not topic:
            st.warning("请输入内容主题")

    # 底部提示
    st.markdown("---")
    with st.expander("💡 使用提示"):
        st.markdown("""
        ### 模型选择建议
        - **Qwen2.5-7B**: 速度快，适合简单内容
        - **Qwen2.5-14B/32B**: 平衡质量和速度，推荐日常使用
        - **Qwen2.5-72B**: 最高质量，适合重要内容
        - **DeepSeek**: 中文理解能力强
        - **Moonshot**: 支持超长上下文

        ### 输出长度说明
        - 512 tokens ≈ 300-500 中文字
        - 2048 tokens ≈ 1500-2000 中文字
        - 4096 tokens ≈ 3000-4000 中文字

        ### 创意度调节
        - 0.3-0.5: 更稳定、确定性强
        - 0.7: 平衡创意和准确性（推荐）
        - 0.9-1.0: 更有创意但可能不稳定
        """)
