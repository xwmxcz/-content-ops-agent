"""快速开始示例"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools import ContentGenerator
from src.models import ContentRequest, ContentType, ContentStyle


def example_xiaohongshu():
    """示例：生成小红书文案"""
    print("\n" + "=" * 60)
    print("📱 示例 1: 小红书文案生成")
    print("=" * 60)

    generator = ContentGenerator()

    request = ContentRequest(
        topic="早起的好处和如何养成早起习惯",
        content_type=ContentType.XIAOHONGSHU,
        style=ContentStyle.CASUAL,
        keywords=["早起", "习惯养成", "自律"],
        length="medium",
    )

    result = generator.generate(request)

    print(f"\n✅ 生成成功！\n")
    if result.title:
        print(f"【标题】\n{result.title}\n")
    print(f"【正文】\n{result.content}\n")
    if result.tags:
        print(f"【标签】\n{' '.join(result.tags)}\n")


def example_blog():
    """示例：生成博客文章"""
    print("\n" + "=" * 60)
    print("📝 示例 2: 博客文章生成")
    print("=" * 60)

    generator = ContentGenerator()

    request = ContentRequest(
        topic="Python 异步编程入门指南",
        content_type=ContentType.BLOG,
        style=ContentStyle.PROFESSIONAL,
        keywords=["Python", "异步编程", "asyncio"],
        length="medium",
    )

    result = generator.generate(request)

    print(f"\n✅ 生成成功！\n")
    if result.title:
        print(f"【标题】\n{result.title}\n")
    print(f"【正文】\n{result.content}\n")


def example_weibo():
    """示例：生成微博文案"""
    print("\n" + "=" * 60)
    print("🐦 示例 3: 微博文案生成")
    print("=" * 60)

    generator = ContentGenerator()

    request = ContentRequest(
        topic="AI 技术如何改变我们的生活",
        content_type=ContentType.WEIBO,
        style=ContentStyle.MARKETING,
        keywords=["AI", "人工智能", "科技"],
    )

    result = generator.generate(request)

    print(f"\n✅ 生成成功！\n")
    print(f"{result.content}\n")


def example_batch():
    """示例：批量生成"""
    print("\n" + "=" * 60)
    print("📦 示例 4: 批量生成内容")
    print("=" * 60)

    generator = ContentGenerator()

    requests = [
        ContentRequest(
            topic="健康饮食小贴士",
            content_type=ContentType.XIAOHONGSHU,
            style=ContentStyle.CASUAL,
            length="short",
        ),
        ContentRequest(
            topic="高效学习方法",
            content_type=ContentType.XIAOHONGSHU,
            style=ContentStyle.CASUAL,
            length="short",
        ),
        ContentRequest(
            topic="职场沟通技巧",
            content_type=ContentType.XIAOHONGSHU,
            style=ContentStyle.PROFESSIONAL,
            length="short",
        ),
    ]

    print(f"\n正在批量生成 {len(requests)} 篇内容...\n")
    results = generator.batch_generate(requests)

    print(f"\n✅ 批量生成完成！共生成 {len(results)} 篇内容\n")
    for i, result in enumerate(results, 1):
        print(f"--- 内容 {i} ---")
        if result.title:
            print(f"标题: {result.title}")
        print(f"正文: {result.content[:100]}...")
        print()


if __name__ == "__main__":
    print("\n🚀 Content Ops Agent - 快速开始示例")
    print("\n请选择要运行的示例：")
    print("1. 小红书文案生成")
    print("2. 博客文章生成")
    print("3. 微博文案生成")
    print("4. 批量生成内容")
    print("5. 运行所有示例")

    choice = input("\n请输入选项 (1-5): ").strip()

    if choice == "1":
        example_xiaohongshu()
    elif choice == "2":
        example_blog()
    elif choice == "3":
        example_weibo()
    elif choice == "4":
        example_batch()
    elif choice == "5":
        example_xiaohongshu()
        example_blog()
        example_weibo()
        example_batch()
    else:
        print("❌ 无效选项")
