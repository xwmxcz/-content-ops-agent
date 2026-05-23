import pytest

from src.utils import config
from src.utils.config import Config
from src.llm.litellm_client import _format_provider_error


def test_litellm_model_names_are_provider_prefixed_when_required():
    assert config.get_litellm_model("siliconflow", "Qwen/Qwen2.5-7B-Instruct") == (
        "openai/Qwen/Qwen2.5-7B-Instruct"
    )
    assert config.get_litellm_model("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"
    assert config.get_litellm_model("moonshot", "moonshot-v1-8k") == "moonshot/moonshot-v1-8k"
    assert config.get_litellm_model("newapi", "Kimi-K2.6") == "openai/Kimi-K2.6"


def test_newapi_api_base_normalizes_v1_suffix(monkeypatch):
    monkeypatch.setattr(Config, "NEWAPI_BASE_URL", "https://gateway.example.com")
    assert config.get_provider_api_base("newapi") == "https://gateway.example.com/v1"

    monkeypatch.setattr(Config, "NEWAPI_BASE_URL", "https://gateway.example.com/v1")
    assert config.get_provider_api_base("newapi") == "https://gateway.example.com/v1"

    monkeypatch.setattr(Config, "NEWAPI_BASE_URL", "https://gateway.example.com/v1/")
    assert config.get_provider_api_base("newapi") == "https://gateway.example.com/v1"

    monkeypatch.setattr(Config, "NEWAPI_BASE_URL", "")
    assert config.get_provider_api_base("newapi") is None


def test_claude_litellm_model_name_is_not_rewritten():
    assert config.get_litellm_model("claude", "claude-sonnet-4-20250514") == "claude-sonnet-4-20250514"


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="Unknown provider"):
        config.get_model("unknown")


def test_llm_timeout_is_positive():
    assert config.LLM_TIMEOUT_SECONDS > 0


def test_format_provider_error_extracts_upstream_json_body():
    raw = (
        "litellm.ServiceUnavailableError: ServiceUnavailableError: OpenAIException - "
        '{"error":{"code":"model_not_found","message":"分组 claude 下模型 gpt-4o-mini 无可用渠道","type":"new_api_error"}}\n'
        "Received Model Group=openai/gpt-4o-mini\n"
        "Available Model Group Fallbacks=None\n"
        "Error Type: status code: 503"
    )
    formatted = _format_provider_error("newapi", RuntimeError(raw))
    assert formatted == "newapi: HTTP 503 分组 claude 下模型 gpt-4o-mini 无可用渠道"


def test_format_provider_error_strips_litellm_wrapping_when_no_json_body():
    raw = "litellm.APIError: APIError: OpenAIException - openai_error"
    formatted = _format_provider_error("newapi", RuntimeError(raw))
    assert formatted == "newapi: openai_error"


def test_format_provider_error_falls_back_to_class_name_for_empty():
    formatted = _format_provider_error("claude", RuntimeError(""))
    assert formatted == "claude: RuntimeError"
