from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
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
    keywords: Optional[List[str]] = None  # 关键词
    length: Optional[str] = "medium"  # 长度: short/medium/long
    tone: Optional[str] = None  # 语气
    target_audience: Optional[str] = None  # 目标受众


@dataclass
class GeneratedContent:
    """生成的内容"""
    content: str  # 内容正文
    title: Optional[str] = None  # 标题
    tags: Optional[List[str]] = None  # 标签
    content_type: Optional[ContentType] = None  # 内容类型
    created_at: datetime = None  # 创建时间
    metadata: Optional[dict] = None  # 元数据

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
