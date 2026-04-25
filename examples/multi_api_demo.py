"""多 API 对比示例"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools import ContentGenerator
from src.models import ContentRequest, ContentType, ContentStyle
from src.llm import LLMFactory


def compare_providers():
    """对比不同提供商的生成效果"""
    print("\n" + "=" * 60)
    print("🔄 多 API 提供商对比")
    print("=" * 60)

    # 测试请求
    request = ContentRequest(
        topic="如何提高工作效率",
        content_type=ContentType.XIAOHONGSHU,
        style=ContentStyle.CASUAL,
        keywords=["效率", "时间管理"],
        length="short",
    )

    providers = ["claude", "siliconflow", "deepseek", "moonshot"]

    print(f"\n📝 测试主题: {request.topic}")
    print(f"   内容类型: {request.content_type.value}")
    print(f"   风格: {request.style.value}\n")

    for provider in providers:
        print(f"\n{'=' * 60}")
        print(f"🤖 提供商: {provider.upper()}")
        print("=" * 60)

        try:
            # 创建生成器（需要在 .env 中配置对应的 API Key）
            generator = ContentGenerator(provider=provider)

            # 生成内容
            result = generator.generate(request)

            print(f"\n✅ 生成成功\n")
            if result.title:
                print(f"【标题】\n{result.title}\n")
            print(f"【正文】\n{result.content}\n")
            if result.tags:
                print(f"【标签】\n{' '.join(result.tags)}\n")

        except ValueError as e:
            print(f"⚠️  跳过: {e}")
        except Exception as e:
            print(f"❌ 生成失败: {e}")


def show_supported_providers():
    """显示支持的提供商"""
    print("\n" + "=" * 60)
    print("📋 支持的 LLM 提供商")
    print("=" * 60)

    providers_info = [
        {
            "name": "Claude (Anthropic)",
            "provider": "claude",
            "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
            "pricing": "Input: $3/1M, Output: $15/1M",
            "features": "最强大，质量最高",
        },
        {
            "name": "硅基流动 (SiliconFlow)",
            "provider": "siliconflow",
            "models": ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-72B-Instruct"],
            "pricing": "约 ¥0.35/1M tokens",
            "features": "国内访问快，价格便宜",
        },
        {
            "name": "DeepSeek",
            "provider": "deepseek",
            "models": ["deepseek-chat"],
            "pricing": "Input: ¥1/1M, Output: ¥2/1M",
            "features": "性价比高，中文友好",
        },
        {
            "name": "Moonshot (Kimi)",
            "provider": "moonshot",
            "models": ["moonshot-v1-8k", "moonshot-v1-32k"],
            "pricing": "约 ¥12/1M tokens",
            "features": "长上下文，中文优秀",
        },
    ]

    for info in providers_info:
        print(f"\n🤖 {info['name']}")
        print(f"   Provider: {info['provider']}")
        print(f"   Models: {', '.join(info['models'])}")
        print(f"   Pricing: {info['pricing']}")
        print(f"   Features: {info['features']}")

    print("\n" + "=" * 60)
    print("\n💡 使用方法:")
    print("   1. 在 .env 中设置 LLM_PROVIDER=<provider>")
    print("   2. 配置对应的 API Key")
    print("   3. 运行程序即可\n")


def test_cost_estimation():
    """测试成本估算"""
    print("\n" + "=" * 60)
    print("💰 成本估算对比")
    print("=" * 60)

    # 假设生成 1000 字内容
    input_tokens = 500  # 约 prompt
    output_tokens = 1500  # 约 1000 字中文

    providers = ["claude", "siliconflow", "deepseek", "moonshot"]

    print(f"\n假设场景: 生成 1000 字内容")
    print(f"   Input tokens: {input_tokens}")
    print(f"   Output tokens: {output_tokens}\n")

    for provider in providers:
        try:
            from src.llm import LLMFactory

            # 创建客户端（使用假的 API Key 仅用于成本估算）
            client = LLMFactory.create_client(provider, "dummy_key")
            cost = client.estimate_cost(input_tokens, output_tokens)

            print(f"{provider.upper():15} ${cost:.6f} (约 ¥{cost * 7:.4f})")
        except Exception as e:
            print(f"{provider.upper():15} 估算失败: {e}")

    print("\n💡 提示:")
    print("   - 批量生成时使用便宜的 API（如 SiliconFlow、DeepSeek）")
    print("   - 重要内容使用高质量 API（如 Claude）")
    print("   - 可以混合使用，平衡成本和质量\n")


if __name__ == "__main__":
    print("\n🚀 Content Ops Agent - 多 API 对比示例")
    print("\n请选择功能：")
    print("1. 查看支持的提供商")
    print("2. 对比不同提供商的生成效果")
    print("3. 成本估算对比")
    print("4. 运行所有功能")

    choice = input("\n请输入选项 (1-4): ").strip()

    if choice == "1":
        show_supported_providers()
    elif choice == "2":
        compare_providers()
    elif choice == "3":
        test_cost_estimation()
    elif choice == "4":
        show_supported_providers()
        test_cost_estimation()
        compare_providers()
    else:
        print("❌ 无效选项")
