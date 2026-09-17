from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ContentType(str, Enum):
    """内容类型"""

    XIAOHONGSHU = "xiaohongshu"  # 小红书
    WEIBO = "weibo"  # 微博
    BLOG = "blog"  # 博客文章
    VIDEO_SCRIPT = "video_script"  # 视频脚本
    TWITTER = "twitter"  # Twitter


class ContentStyle(str, Enum):
    """内容风格"""

    PROFESSIONAL = "professional"  # 专业
    CASUAL = "casual"  # 轻松
    MARKETING = "marketing"  # 营销
    STORYTELLING = "storytelling"  # 故事性


@dataclass
class ContentRequest:
    """内容生成请求"""

    topic: str  # 主题
    content_type: ContentType  # 内容类型
    style: ContentStyle = ContentStyle.CASUAL  # 风格
    keywords: list[str] | None = None  # 关键词
    length: str | None = "medium"  # 长度: short/medium/long
    tone: str | None = None  # 语气
    target_audience: str | None = None  # 目标受众


@dataclass
class GeneratedContent:
    """生成的内容"""

    content: str  # 内容正文
    title: str | None = None  # 标题
    tags: list[str] | None = None  # 标签
    content_type: ContentType | None = None  # 内容类型
    created_at: datetime = None  # 创建时间
    metadata: dict | None = None  # 元数据

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
