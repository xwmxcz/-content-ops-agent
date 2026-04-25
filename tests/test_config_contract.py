from src.tools.content_generator import ContentGenerator


def test_content_generator_uses_explicit_provider_credentials():
    generator = ContentGenerator(
        provider="siliconflow",
        api_key="test-key",
        model="Qwen/Qwen2.5-7B-Instruct",
    )

    assert generator.provider == "siliconflow"
    assert generator.api_key == "test-key"
    assert generator.model == "Qwen/Qwen2.5-7B-Instruct"
