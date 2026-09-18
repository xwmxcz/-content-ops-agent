import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.llm.litellm_client import _format_provider_error
from src.utils import config
from src.utils.config import Config


@pytest.fixture(autouse=True)
def isolated_runtime_auth(monkeypatch):
    for name in ("AUTH_ENABLED", "AUTH_USERNAME", "AUTH_PASSWORD", "AUTH_STREAM_TICKET_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Config, "AUTH_SECRET_KEY", "test-signing-key")


@pytest.mark.parametrize("profile", ["development", "test", "production"])
@pytest.mark.parametrize("name", ["AUTH_ENABLED", "AUTH_USERNAME", "AUTH_PASSWORD"])
@pytest.mark.parametrize("value", ["", "legacy-value"])
def test_removed_account_settings_fail_with_migration_error(monkeypatch, profile, name, value):
    monkeypatch.setattr(Config, "APP_ENV", profile)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="migration required") as exc_info:
        Config.validate_runtime()
    assert name in str(exc_info.value)
    assert not hasattr(Config, name)


@pytest.mark.parametrize("profile", ["development", "test"])
@pytest.mark.parametrize("secret", ["", "   "])
def test_local_profiles_require_nonempty_signing_key(monkeypatch, profile, secret):
    monkeypatch.setattr(Config, "APP_ENV", profile)
    monkeypatch.setattr(Config, "AUTH_SECRET_KEY", secret)
    with pytest.raises(ValueError, match="AUTH_SECRET_KEY is required"):
        Config.validate_runtime()


def test_stream_ticket_setting_has_no_legacy_alias(monkeypatch):
    monkeypatch.setenv("AUTH_STREAM_TICKET_SECONDS", "90")
    with pytest.raises(ValueError, match="use AUTH_RESOURCE_TICKET_SECONDS"):
        Config.validate_runtime()


def test_resource_ticket_seconds_uses_canonical_setting():
    env = dict(os.environ, PYTHON_DOTENV_DISABLED="1", AUTH_RESOURCE_TICKET_SECONDS="73")
    result = subprocess.run(
        [sys.executable, "-c", "from src.utils import config; print(config.AUTH_RESOURCE_TICKET_SECONDS)"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "73"


@pytest.mark.parametrize("filename", [".env.example", ".env.docker.example", ".env.postgres-rq"])
def test_env_templates_require_signing_key_without_environment_accounts(filename):
    source = (Path(__file__).resolve().parents[1] / filename).read_text(encoding="utf-8")
    assert any(line.startswith("AUTH_SECRET_KEY=") for line in source.splitlines())
    assert not any(name in source for name in ("AUTH_ENABLED", "AUTH_USERNAME", "AUTH_PASSWORD"))


def test_unset_runtime_profile_defaults_to_fail_closed_production():
    env = dict(os.environ)
    for name in (
        "APP_ENV",
        "SCHEMA_MANAGEMENT",
        "AUTH_ENABLED",
        "AUTH_USERNAME",
        "AUTH_PASSWORD",
        "AUTH_STREAM_TICKET_SECONDS",
        "AUTH_SECRET_KEY",
        "DATABASE_URL",
        "CORS_ORIGINS",
    ):
        env.pop(name, None)
    env["PYTHON_DOTENV_DISABLED"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from src.utils import config; "
                "print(config.APP_ENV, config.SCHEMA_MANAGEMENT); "
                "config.validate_runtime()"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert result.stdout.strip() == "production validate"
    assert "Unsafe production configuration" in result.stderr


def test_development_runtime_accepts_required_signing_key(monkeypatch):
    monkeypatch.setattr(Config, "APP_ENV", "development")
    monkeypatch.setattr(Config, "SCHEMA_MANAGEMENT", "create")
    assert Config.validate_runtime() is True


def test_production_runtime_fails_closed_on_unsafe_defaults(monkeypatch):
    monkeypatch.setattr(Config, "APP_ENV", "production")
    monkeypatch.setattr(Config, "SCHEMA_MANAGEMENT", "create")
    monkeypatch.setattr(Config, "AUTH_SECRET_KEY", "")
    monkeypatch.setattr(Config, "DEBUG", True)
    monkeypatch.setattr(Config, "CORS_ORIGINS", ["http://localhost:5173"])
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql+psycopg://content_ops:content_ops@db/content_ops")
    monkeypatch.setattr(Config, "JOB_QUEUE_MODE", "rq")
    monkeypatch.setattr(Config, "REDIS_URL", "redis://:content_ops@redis:6379/0")

    with pytest.raises(ValueError, match="Unsafe production configuration") as exc_info:
        Config.validate_runtime()
    message = str(exc_info.value)
    assert "AUTH_SECRET_KEY" in message
    assert "SCHEMA_MANAGEMENT" in message
    assert "DATABASE_URL" in message
    assert "REDIS_URL" in message


def test_production_runtime_accepts_explicit_safe_configuration(monkeypatch):
    monkeypatch.setattr(Config, "APP_ENV", "production")
    monkeypatch.setattr(Config, "SCHEMA_MANAGEMENT", "validate")
    monkeypatch.setattr(Config, "AUTH_SECRET_KEY", "9a7f3c1e5b8d2f4a6c0e1b3d5f7a9c2e")
    monkeypatch.setattr(Config, "DEBUG", False)
    monkeypatch.setattr(Config, "ENFORCE_HTTPS", True)
    monkeypatch.setattr(Config, "CORS_ORIGINS", ["https://content.example.com"])
    monkeypatch.setattr(
        Config,
        "DATABASE_URL",
        "postgresql+psycopg://content_ops:D8b!3qZ7mP2xL9vR@db/content_ops",
    )
    monkeypatch.setattr(Config, "JOB_QUEUE_MODE", "rq")
    monkeypatch.setattr(Config, "REDIS_URL", "redis://:N4k@8sW1cT6yH3uQ@redis:6379/0")
    assert Config.validate_runtime() is True


def test_production_rejects_long_low_entropy_and_reused_secrets(monkeypatch):
    monkeypatch.setattr(Config, "APP_ENV", "production")
    monkeypatch.setattr(Config, "SCHEMA_MANAGEMENT", "validate")
    monkeypatch.setattr(Config, "AUTH_SECRET_KEY", "A" * 40)
    monkeypatch.setattr(Config, "DEBUG", False)
    monkeypatch.setattr(Config, "ENFORCE_HTTPS", True)
    monkeypatch.setattr(Config, "CORS_ORIGINS", ["https://content.example.com"])
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql+psycopg://u:" + "A" * 40 + "@db/app")
    monkeypatch.setattr(Config, "JOB_QUEUE_MODE", "background")
    with pytest.raises(ValueError) as exc_info:
        Config.validate_runtime()
    message = str(exc_info.value)
    assert "high-entropy AUTH_SECRET_KEY" in message
    assert "must be distinct" in message


def test_compose_default_path_validates_production_before_migrating_or_serving():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    assert "APP_ENV: ${APP_ENV:-production}" in compose
    assert "AUTH_SECRET_KEY: ${AUTH_SECRET_KEY:-}" in compose
    assert not any(name in compose for name in ("AUTH_ENABLED", "AUTH_USERNAME", "AUTH_PASSWORD"))
    assert "ENFORCE_HTTPS: ${ENFORCE_HTTPS:-true}" in compose
    assert "config.validate_runtime()' && alembic upgrade head" in compose
    assert "127.0.0.1:${FRONTEND_PORT:-8088}:80" in compose
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
    assert "APP_ENV=production" in dockerfile
    assert "SCHEMA_MANAGEMENT=validate" in dockerfile


def test_litellm_model_names_are_provider_prefixed_when_required():
    assert config.get_litellm_model("siliconflow", "Qwen/Qwen2.5-7B-Instruct") == ("openai/Qwen/Qwen2.5-7B-Instruct")
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
