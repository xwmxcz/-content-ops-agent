import pytest

from src.utils import config


def test_litellm_model_names_are_provider_prefixed_when_required():
    assert config.get_litellm_model("siliconflow", "Qwen/Qwen2.5-7B-Instruct") == (
        "openai/Qwen/Qwen2.5-7B-Instruct"
    )
    assert config.get_litellm_model("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"
    assert config.get_litellm_model("moonshot", "moonshot-v1-8k") == "moonshot/moonshot-v1-8k"


def test_claude_litellm_model_name_is_not_rewritten():
    assert config.get_litellm_model("claude", "claude-sonnet-4-20250514") == "claude-sonnet-4-20250514"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="Unknown provider"):
        config.get_model("unknown")


def test_llm_timeout_is_positive():
    assert config.LLM_TIMEOUT_SECONDS > 0
