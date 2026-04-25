"""测试脚本 - 验证项目配置"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_imports():
    """测试导入"""
    print("🔍 测试模块导入...")
    try:
        from src.models import ContentRequest, ContentType, ContentStyle, GeneratedContent
        from src.tools import ContentGenerator, PromptTemplates
        from src.utils import config
        print("✅ 所有模块导入成功")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False


def test_config():
    """测试配置"""
    print("\n🔍 测试配置...")
    try:
        from src.utils import config

        print(f"   DEBUG: {config.DEBUG}")
        print(f"   LOG_LEVEL: {config.LOG_LEVEL}")
        provider = config.LLM_PROVIDER
        print(f"   LLM_PROVIDER: {provider}")
        print(f"   MODEL: {config.get_model(provider)}")

        if config.has_provider_key(provider):
            print(f"   API_KEY: {'*' * 20} (已配置)")
        else:
            print(f"   ⚠️  {provider} API Key: 未配置")
            print("   请在 .env 文件中配置当前 LLM_PROVIDER 对应的 API Key")
            return False

        print("✅ 配置检查通过")
        return True
    except Exception as e:
        print(f"❌ 配置检查失败: {e}")
        return False


def test_models():
    """测试数据模型"""
    print("\n🔍 测试数据模型...")
    try:
        from src.models import ContentRequest, ContentType, ContentStyle

        request = ContentRequest(
            topic="测试主题",
            content_type=ContentType.XIAOHONGSHU,
            style=ContentStyle.CASUAL,
            keywords=["测试"],
            length="short"
        )

        print(f"   创建请求: {request.topic}")
        print(f"   类型: {request.content_type.value}")
        print(f"   风格: {request.style.value}")
        print("✅ 数据模型测试通过")
        return True
    except Exception as e:
        print(f"❌ 数据模型测试失败: {e}")
        return False


def test_generator_init():
    """测试生成器初始化"""
    print("\n🔍 测试生成器初始化...")
    try:
        from src.tools import ContentGenerator
        generator = ContentGenerator()
        print("✅ 生成器初始化成功")
        return True
    except ValueError as e:
        print(f"⚠️  生成器初始化失败: {e}")
        print("   请确保已配置 ANTHROPIC_API_KEY")
        return False
    except Exception as e:
        print(f"❌ 生成器初始化失败: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 Content Ops Agent - 项目测试")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(("模块导入", test_imports()))
    results.append(("配置检查", test_config()))
    results.append(("数据模型", test_models()))
    results.append(("生成器初始化", test_generator_init()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！项目配置正确。")
        print("\n下一步:")
        print("1. 运行 'python run.py' 生成第一个内容")
        print("2. 运行 'python examples/quick_start.py' 查看更多示例")
    else:
        print("\n⚠️  部分测试失败，请检查配置。")
        print("\n常见问题:")
        print("1. 确保已安装所有依赖: pip install -r requirements.txt")
        print("2. 确保已配置 .env 文件中的 ANTHROPIC_API_KEY")

    print("=" * 60)


if __name__ == "__main__":
    main()
