"""内容生成和优化工具"""
from typing import Optional
from langchain_core.tools import tool

from src.models import ContentRequest, ContentType, ContentStyle
from src.tools.content_generator import ContentGenerator
from src.storage import ContentStore


_store = None


def get_store() -> ContentStore:
    global _store
    if _store is None:
        _store = ContentStore()
    return _store


@tool
def generate_content(topic: str, content_type: str, style: str = "casual",
                    keywords: Optional[str] = None, length: str = "medium") -> str:
    """生成新内容"""
    try:
        content_type_enum = ContentType(content_type)
        style_enum = ContentStyle(style)
        keywords_list = [k.strip() for k in keywords.split(",")] if keywords else None

        request = ContentRequest(
            topic=topic,
            content_type=content_type_enum,
            style=style_enum,
            keywords=keywords_list,
            length=length
        )

        generator = ContentGenerator()
        result = generator.generate(request)

        store = get_store()
        content_id = store.save_content(
            result,
            llm_provider=generator.provider,
            model_name=generator.model,
            style=style_enum.value,
            keywords=keywords_list,
        )

        output = f"✅ 内容生成成功！(ID: {content_id})\n\n"
        if result.title:
            output += f"【标题】\n{result.title}\n\n"
        output += f"【正文】\n{result.content}\n\n"
        if result.tags:
            output += f"【标签】\n{' '.join(result.tags)}\n\n"
        output += f"💾 内容已保存，ID: {content_id}"
        return output

    except Exception as e:
        return f"❌ 生成失败: {str(e)}"


@tool
def refine_content(content_id: int, instruction: str) -> str:
    """按指令改写已有内容"""
    try:
        store = get_store()
        original = store.get_content(content_id)
        if not original:
            return f"❌ 找不到 ID 为 {content_id} 的内容"

        from src.tools.content_generator import ContentGenerator

        system_prompt = "你是一位专业的内容编辑，擅长根据指令改写内容。"
        user_prompt = f"""请根据以下指令改写内容：

指令：{instruction}

原内容：
{original['content']}

请直接输出改写后的内容。"""

        generator = ContentGenerator()
        refined_text = generator.client.generate(system_prompt, user_prompt, temperature=0.7, max_tokens=4096)

        from src.models import GeneratedContent, ContentType
        from datetime import datetime

        refined_content = GeneratedContent(
            content=refined_text,
            title=original.get('title'),
            tags=original.get('tags'),
            content_type=ContentType(original['content_type']),
            created_at=datetime.now()
        )

        new_id = store.save_content(
            refined_content,
            llm_provider=generator.provider,
            model_name=generator.model,
            parent_id=content_id,
            style=original.get("style", "casual"),
            keywords=original.get("keywords", []),
        )
        store.update_content(new_id, status="refined")

        return f"✅ 内容改写成功！(新 ID: {new_id})\n\n【改写后内容】\n{refined_text}\n\n💾 已保存为新版本，ID: {new_id}"

    except Exception as e:
        return f"❌ 改写失败: {str(e)}"


@tool
def rewrite_with_style(content_id: int, new_style: str) -> str:
    """切换风格重写内容"""
    try:
        style_enum = ContentStyle(new_style)
        instruction = f"请将内容改写为{style_enum.value}风格"
        return refine_content(content_id, instruction)
    except ValueError:
        return f"❌ 不支持的风格: {new_style}"


@tool
def generate_title_options(topic: str, content_type: str, count: int = 5) -> str:
    """生成多个标题供选择"""
    try:
        from src.tools.content_generator import ContentGenerator

        generator = ContentGenerator()
        system_prompt = "你是一位专业的标题创作专家，擅长创作吸引眼球的标题。"
        user_prompt = f"请为{content_type}平台创作{count}个关于「{topic}」的标题。\n\n请按以下格式输出：\n1. [标题1]\n2. [标题2]\n..."

        result = generator.client.generate(system_prompt, user_prompt, temperature=0.9, max_tokens=1024)
        return f"✅ 标题生成成功！\n\n{result}"

    except Exception as e:
        return f"❌ 生成失败: {str(e)}"


@tool
def optimize_seo(content_id: int) -> str:
    """SEO 关键词优化建议"""
    try:
        store = get_store()
        content = store.get_content(content_id)
        if not content:
            return f"❌ 找不到 ID 为 {content_id} 的内容"

        from src.tools.content_generator import ContentGenerator

        generator = ContentGenerator()
        system_prompt = "你是一位 SEO 专家，擅长关键词优化和内容 SEO 分析。"
        user_prompt = f"""请分析以下内容的 SEO 优化建议：

标题：{content.get('title', '无')}
正文：{content['content'][:500]}...

请提供：核心关键词建议、标题优化建议、内容结构优化建议"""

        result = generator.client.generate(system_prompt, user_prompt, temperature=0.5, max_tokens=2048)
        return f"✅ SEO 分析完成！\n\n{result}"

    except Exception as e:
        return f"❌ 分析失败: {str(e)}"


@tool
def view_content(content_id: int) -> str:
    """查看内容详情"""
    try:
        store = get_store()
        content = store.get_content(content_id)
        if not content:
            return f"❌ 找不到 ID 为 {content_id} 的内容"

        output = f"📄 内容详情 (ID: {content_id})\n\n"
        if content.get('title'):
            output += f"【标题】\n{content['title']}\n\n"
        output += f"【正文】\n{content['content']}\n\n"
        output += f"【类型】{content['content_type']}\n"
        output += f"【风格】{content['style']}\n"
        output += f"【状态】{content['status']}\n"
        if content.get('tags'):
            output += f"【标签】{', '.join(content['tags'])}\n"
        return output

    except Exception as e:
        return f"❌ 查看失败: {str(e)}"


@tool
def list_recent_contents(limit: int = 10) -> str:
    """列出最近的内容"""
    try:
        store = get_store()
        contents = store.list_contents(limit=limit)

        if not contents:
            return "📭 还没有任何内容"

        output = f"📚 最近的 {len(contents)} 条内容：\n\n"
        for c in contents:
            output += f"ID: {c['id']} | {c['content_type']} | {c['status']}\n"
            if c.get('title'):
                output += f"标题: {c['title']}\n"
            output += f"预览: {c['content']}\n"
            output += f"创建: {c.get('created_at', '未知')}\n"
            output += "-" * 50 + "\n"
        return output

    except Exception as e:
        return f"❌ 查询失败: {str(e)}"
