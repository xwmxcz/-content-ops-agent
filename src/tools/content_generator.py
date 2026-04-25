"""内容生成器 - 核心功能"""
import re
from typing import Optional
from src.models import ContentRequest, GeneratedContent, ContentType
from src.utils import config
from src.tools.prompt_templates import PromptTemplates
from src.llm import LLMFactory


class ContentGenerator:
    """内容生成器"""

    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        初始化

        Args:
            provider: LLM 提供商 (claude, siliconflow, deepseek, moonshot)
                     如果为 None，使用配置文件中的设置
            api_key: API Key，如果为 None，使用配置文件中的设置
            model: 模型名称，如果为 None，使用配置文件中的设置
        """
        # 使用参数或配置文件中的设置
        self.provider = (provider or config.LLM_PROVIDER).lower()
        self.api_key = api_key or config.get_api_key(self.provider)
        if not self.api_key:
            config.validate(self.provider)
        self.model = model or config.get_model(self.provider)

        # 创建 LLM 客户端
        self.client = LLMFactory.create_client(
            provider=self.provider,
            api_key=self.api_key,
            model=self.model
        )

        self.templates = PromptTemplates()

        print(f"✓ 使用 {self.client.get_model_name()}")

    def generate(self, request: ContentRequest) -> GeneratedContent:
        """生成内容"""
        # 构建 prompt
        system_prompt = self.templates.get_system_prompt(
            request.content_type, request.style
        )
        user_prompt = self._build_user_prompt(request)

        # 调用 LLM API
        content_text = self.client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
        )

        # 解析响应
        return self._parse_response(content_text, request.content_type)

    def _build_user_prompt(self, request: ContentRequest) -> str:
        """构建用户 prompt"""
        if request.content_type == ContentType.XIAOHONGSHU:
            return self.templates.get_xiaohongshu_prompt(
                request.topic, request.keywords, request.length
            )
        elif request.content_type == ContentType.WEIBO:
            return self.templates.get_weibo_prompt(request.topic, request.keywords)
        elif request.content_type == ContentType.BLOG:
            return self.templates.get_blog_prompt(
                request.topic, request.keywords, request.length
            )
        elif request.content_type == ContentType.VIDEO_SCRIPT:
            return self.templates.get_video_script_prompt(request.topic, request.length)
        else:
            raise ValueError(f"Unsupported content type: {request.content_type}")

    def _parse_response(
        self, content_text: str, content_type: ContentType
    ) -> GeneratedContent:
        """解析 AI 响应"""
        title = None
        content = content_text
        tags = None

        # 提取标题
        title_match = re.search(r"【标题】\s*\n(.+?)(?:\n|$)", content_text)
        if title_match:
            title = title_match.group(1).strip()

        # 提取正文
        content_match = re.search(
            r"【正文】\s*\n(.*?)(?:【标签】|$)", content_text, re.DOTALL
        )
        if content_match:
            content = content_match.group(1).strip()
        elif not title_match:  # 如果没有结构化格式，直接使用全文
            content = content_text.strip()

        # 提取标签（小红书）
        if content_type == ContentType.XIAOHONGSHU:
            tags_match = re.search(r"【标签】\s*\n(.+?)$", content_text, re.DOTALL)
            if tags_match:
                tags_text = tags_match.group(1).strip()
                tags = [tag.strip() for tag in re.split(r"[,，\s]+", tags_text) if tag.strip()]

        return GeneratedContent(
            content=content,
            title=title,
            tags=tags,
            content_type=content_type,
            metadata={"raw_response": content_text},
        )

    def batch_generate(
        self, requests: list[ContentRequest]
    ) -> list[GeneratedContent]:
        """批量生成内容"""
        results = []
        for request in requests:
            try:
                result = self.generate(request)
                results.append(result)
            except Exception as e:
                print(f"生成失败: {request.topic} - {e}")
                continue
        return results
