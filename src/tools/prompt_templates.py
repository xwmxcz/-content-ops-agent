"""Prompt 模板"""
from src.models import ContentType, ContentStyle


class PromptTemplates:
    """内容生成的 Prompt 模板"""

    @staticmethod
    def get_system_prompt(content_type: ContentType, style: ContentStyle) -> str:
        """获取系统提示词"""
        base = "你是一位专业的内容创作专家，擅长创作高质量、吸引人的内容。"

        style_prompts = {
            ContentStyle.PROFESSIONAL: "你的写作风格专业、严谨，注重事实和逻辑。",
            ContentStyle.CASUAL: "你的写作风格轻松、亲切，像朋友聊天一样自然。",
            ContentStyle.MARKETING: "你的写作风格具有营销性，善于激发读者的兴趣和行动欲望。",
            ContentStyle.STORYTELLING: "你的写作风格富有故事性，善于用故事打动人心。",
        }

        return f"{base}\n{style_prompts.get(style, '')}"

    @staticmethod
    def get_xiaohongshu_prompt(topic: str, keywords: list = None, length: str = "medium") -> str:
        """小红书文案生成 Prompt"""
        length_guide = {
            "short": "100-200字",
            "medium": "200-400字",
            "long": "400-600字"
        }

        keywords_text = f"关键词：{', '.join(keywords)}" if keywords else ""

        return f"""请为小红书平台创作一篇关于「{topic}」的内容。

要求：
1. 标题：吸引眼球，使用emoji，控制在20字以内
2. 正文：{length_guide.get(length, '200-400字')}
3. 风格：真实、接地气、有共鸣感
4. 结构：开头抓人 → 干货内容 → 互动引导
5. 标签：提供5-8个相关标签
{keywords_text}

请按以下格式输出：
【标题】
[标题内容]

【正文】
[正文内容]

【标签】
[标签列表，用空格分隔]
"""

    @staticmethod
    def get_weibo_prompt(topic: str, keywords: list = None) -> str:
        """微博文案生成 Prompt"""
        keywords_text = f"关键词：{', '.join(keywords)}" if keywords else ""

        return f"""请为微博平台创作一条关于「{topic}」的内容。

要求：
1. 字数：140字以内（可适当超出）
2. 风格：简洁有力，观点鲜明
3. 技巧：使用话题标签 #话题#，适当使用emoji
4. 互动：引导转发、评论或点赞
{keywords_text}

直接输出微博内容即可。
"""

    @staticmethod
    def get_blog_prompt(topic: str, keywords: list = None, length: str = "medium") -> str:
        """博客文章生成 Prompt"""
        length_guide = {
            "short": "500-800字",
            "medium": "800-1500字",
            "long": "1500-3000字"
        }

        keywords_text = f"关键词：{', '.join(keywords)}" if keywords else ""

        return f"""请创作一篇关于「{topic}」的博客文章。

要求：
1. 标题：清晰明确，包含关键词
2. 字数：{length_guide.get(length, '800-1500字')}
3. 结构：引言 → 主体（2-4个小节）→ 总结
4. 风格：有深度、有见解、有价值
5. SEO：自然融入关键词
{keywords_text}

请按以下格式输出：
【标题】
[标题内容]

【正文】
[正文内容，使用 Markdown 格式]
"""

    @staticmethod
    def get_video_script_prompt(topic: str, length: str = "medium") -> str:
        """视频脚本生成 Prompt"""
        length_guide = {
            "short": "1-3分钟",
            "medium": "3-5分钟",
            "long": "5-10分钟"
        }

        return f"""请为「{topic}」创作一个视频脚本。

要求：
1. 时长：{length_guide.get(length, '3-5分钟')}
2. 结构：开场（吸引注意）→ 主体（核心内容）→ 结尾（行动号召）
3. 风格：口语化、节奏感强
4. 标注：画面提示、停顿位置

请按以下格式输出：
【标题】
[视频标题]

【脚本】
[开场]
[画面：...]
[文案：...]

[主体]
[画面：...]
[文案：...]

[结尾]
[画面：...]
[文案：...]
"""
