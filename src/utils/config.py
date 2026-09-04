import ipaddress
import math
import os
from collections import Counter
from urllib.parse import unquote, urlsplit

from dotenv import load_dotenv

load_dotenv()


class Config:
    """应用配置"""

    # Runtime profile. Backward-compatible schema creation and disabled auth are
    # available only in the explicit development/test profiles. Production is
    # validated fail-closed during API/worker startup.
    # Omission is production, not development. Local compatibility must be an
    # explicit APP_ENV=development/test choice (the checked-in env examples do
    # this), so direct image/Gunicorn/server.py entrypoints also fail closed.
    APP_ENV = os.getenv("APP_ENV", "production").lower()
    SCHEMA_MANAGEMENT = os.getenv(
        "SCHEMA_MANAGEMENT",
        "create" if APP_ENV in {"development", "test"} else "validate",
    ).lower()

    # LLM Provider Settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude").lower()  # claude, siliconflow, deepseek, moonshot

    # API Keys
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY")
    NEWAPI_API_KEY = os.getenv("NEWAPI_API_KEY")

    # Model Settings
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "zai-org/GLM-4.5-Air")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    MOONSHOT_MODEL = os.getenv("MOONSHOT_MODEL", "moonshot-v1-8k")
    NEWAPI_MODEL = os.getenv("NEWAPI_MODEL", "gpt-4o-mini")

    # LiteLLM / OpenAI-compatible endpoint settings
    SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    MOONSHOT_BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    NEWAPI_BASE_URL = os.getenv("NEWAPI_BASE_URL", "")

    # Generation Settings
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
    LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

    # Chat Agent
    CHAT_PLAN_ENABLED = os.getenv("CHAT_PLAN_ENABLED", "true").lower() == "true"
    # A confirmed write capability is short-lived: an idle thread resumed later
    # must re-propose rather than execute a stale approval.
    ACTION_CAPABILITY_TTL_SECONDS = int(os.getenv("ACTION_CAPABILITY_TTL_SECONDS", "900"))

    # Planner structured output (P1-05). Repair is a fixed pipeline of passes, not a
    # retry loop, so this caps how many of those passes may run before the caller
    # gives up and uses the canonical default plan. The default equals the number of
    # implemented passes; lowering it trades plan fidelity for a faster giving-up.
    PLANNER_MAX_REPAIR_ATTEMPTS = int(os.getenv("PLANNER_MAX_REPAIR_ATTEMPTS", "3"))
    # Ask the provider for JSON directly where it is supported. Kept switchable
    # because a gateway can advertise JSON mode and still reject the parameter,
    # which would otherwise fail every planner call behind that gateway.
    PLANNER_STRUCTURED_OUTPUT_ENABLED = (
        os.getenv("PLANNER_STRUCTURED_OUTPUT_ENABLED", "true").lower() == "true"
    )

    # Authentication
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
    AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
    AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
    AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "")
    AUTH_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440"))
    AUTH_RESOURCE_TICKET_SECONDS = int(
        os.getenv("AUTH_RESOURCE_TICKET_SECONDS", os.getenv("AUTH_STREAM_TICKET_SECONDS", "45"))
    )
    AUTH_MEDIA_TICKET_SECONDS = int(os.getenv("AUTH_MEDIA_TICKET_SECONDS", "300"))

    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://content_ops:content_ops@localhost:5432/content_ops",
    )
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT_SECONDS = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))

    # Background job settings
    JOB_QUEUE_MODE = os.getenv("JOB_QUEUE_MODE", "background").lower()  # background or rq
    JOB_QUEUE_NAME = os.getenv("JOB_QUEUE_NAME", "content_ops")
    JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "300"))
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MAX_PROVIDER_INFLIGHT_JOBS = int(os.getenv("MAX_PROVIDER_INFLIGHT_JOBS", "8"))
    
    # Job retry settings
    JOB_MAX_RETRIES = int(os.getenv("JOB_MAX_RETRIES", "5"))
    JOB_RETRY_INITIAL_DELAY_SECONDS = int(os.getenv("JOB_RETRY_INITIAL_DELAY_SECONDS", "30"))
    JOB_RETRY_MAX_DELAY_SECONDS = int(os.getenv("JOB_RETRY_MAX_DELAY_SECONDS", "480"))  # 8 minutes

    # Job lease settings (P1-04). The lease must outlive the heartbeat interval by
    # a wide margin: a lease shorter than a few heartbeat periods lets one slow
    # database round-trip look like a dead worker and get the job reclaimed while
    # it is still running.
    JOB_LEASE_DURATION_SECONDS = int(os.getenv("JOB_LEASE_DURATION_SECONDS", "300"))
    JOB_HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("JOB_HEARTBEAT_INTERVAL_SECONDS", "30"))
    JOB_REAPER_INTERVAL_SECONDS = int(os.getenv("JOB_REAPER_INTERVAL_SECONDS", "60"))
    JOB_REAPER_BATCH_SIZE = int(os.getenv("JOB_REAPER_BATCH_SIZE", "50"))

    # SSE run streaming (P1-06). Clients treat silence as a stale connection, so
    # the server must emit a keepalive comment well inside the client's staleness
    # budget: a long research step produces no events for minutes, and without a
    # keepalive that is indistinguishable from a dead proxy. The poll interval is
    # how often the event table is swept for new rows.
    SSE_KEEPALIVE_SECONDS = int(os.getenv("SSE_KEEPALIVE_SECONDS", "15"))
    SSE_POLL_INTERVAL_SECONDS = float(os.getenv("SSE_POLL_INTERVAL_SECONDS", "0.4"))
    # Hard ceiling on one subscription. The client reconnects with `after_seq`, so
    # this bounds server-side resource hold time without losing events.
    SSE_STREAM_TIMEOUT_SECONDS = int(os.getenv("SSE_STREAM_TIMEOUT_SECONDS", "600"))

    # Media and MCP integration
    MEDIA_STORAGE_ROOT = os.getenv("MEDIA_STORAGE_ROOT", "data/media")
    MEDIA_MAX_IMAGE_COUNT = int(os.getenv("MEDIA_MAX_IMAGE_COUNT", "9"))
    MEDIA_MAX_VIDEO_SIZE_MB = int(os.getenv("MEDIA_MAX_VIDEO_SIZE_MB", "512"))
    WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "auto").lower()
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
    SEARXNG_BASE_URL = os.getenv("SEARXNG_BASE_URL", "")
    XHS_MCP_ENABLED = os.getenv("XHS_MCP_ENABLED", "true").lower() == "true"
    XHS_MCP_URL = os.getenv("XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    XHS_MCP_TIMEOUT_SECONDS = float(os.getenv("XHS_MCP_TIMEOUT_SECONDS", "120"))

    # Memory system (Hermes-style 4-layer)
    MEMORY_ENABLED = os.getenv("MEMORY_ENABLED", "true").lower() == "true"
    MEMORY_DIR = os.getenv("MEMORY_DIR", "data/memory")
    MEMORY_MD_LIMIT = int(os.getenv("MEMORY_MD_LIMIT", "2200"))
    USER_MD_LIMIT = int(os.getenv("USER_MD_LIMIT", "1375"))
    # Context compressor (layer 4): when in-session messages exceed the threshold
    # ratio of the model's context window, the middle slice is summarized.
    CONTEXT_COMPRESS_ENABLED = os.getenv("CONTEXT_COMPRESS_ENABLED", "true").lower() == "true"
    CONTEXT_COMPRESS_TRIGGER_MESSAGES = int(os.getenv("CONTEXT_COMPRESS_TRIGGER_MESSAGES", "30"))
    CONTEXT_COMPRESS_KEEP_HEAD = int(os.getenv("CONTEXT_COMPRESS_KEEP_HEAD", "4"))
    CONTEXT_COMPRESS_KEEP_TAIL = int(os.getenv("CONTEXT_COMPRESS_KEEP_TAIL", "8"))
    # Memory curator is proposal-only. Thread deletion never invokes it and
    # only confirmed Chat memory tools may apply changes.
    MEMORY_CURATOR_ENABLED = os.getenv("MEMORY_CURATOR_ENABLED", "true").lower() == "true"
    MEMORY_CURATOR_MIN_MESSAGES = int(os.getenv("MEMORY_CURATOR_MIN_MESSAGES", "4"))
    MEMORY_CURATOR_MAX_ACTIONS = int(os.getenv("MEMORY_CURATOR_MAX_ACTIONS", "6"))

    # App Settings
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    API_RELOAD = os.getenv("API_RELOAD", "False").lower() == "true"
    ENFORCE_HTTPS = os.getenv(
        "ENFORCE_HTTPS", "true" if APP_ENV == "production" else "false"
    ).lower() == "true"
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    # X-Forwarded-Proto is accepted only from these explicitly configured
    # proxy source networks. Empty by default: direct entrypoints cannot trust a
    # client-supplied forwarding header. Compose sets its private bridge range.
    TRUSTED_PROXY_CIDRS = [
        value.strip()
        for value in os.getenv("TRUSTED_PROXY_CIDRS", "").split(",")
        if value.strip()
    ]

    @classmethod
    def validate_runtime(cls) -> bool:
        """Validate process-wide deployment settings before serving work."""
        if cls.APP_ENV not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")
        if cls.SCHEMA_MANAGEMENT not in {"create", "validate"}:
            raise ValueError("SCHEMA_MANAGEMENT must be create or validate")

        if cls.APP_ENV != "production":
            return True

        errors: list[str] = []
        if cls.SCHEMA_MANAGEMENT != "validate":
            errors.append("production requires SCHEMA_MANAGEMENT=validate")
        if not cls.AUTH_ENABLED:
            errors.append("production requires AUTH_ENABLED=true")
        if _is_unsafe_secret(cls.AUTH_PASSWORD, minimum=12, minimum_unique=8):
            errors.append("production requires a high-entropy AUTH_PASSWORD of at least 12 characters")
        if _is_unsafe_secret(cls.AUTH_SECRET_KEY, minimum=32, minimum_unique=12):
            errors.append("production requires a high-entropy AUTH_SECRET_KEY of at least 32 characters")
        if cls.DEBUG:
            errors.append("production requires DEBUG=false")
        if not cls.ENFORCE_HTTPS:
            errors.append("production requires ENFORCE_HTTPS=true")
        if not cls.CORS_ORIGINS or any(
            origin == "*"
            or not origin.lower().startswith("https://")
            or "localhost" in origin.lower()
            or "127.0.0.1" in origin
            for origin in cls.CORS_ORIGINS
        ):
            errors.append("production CORS_ORIGINS must contain only explicit HTTPS non-local origins")
        invalid_proxy_cidrs = []
        for value in cls.TRUSTED_PROXY_CIDRS:
            try:
                ipaddress.ip_network(value, strict=False)
            except ValueError:
                invalid_proxy_cidrs.append(value)
        if invalid_proxy_cidrs:
            errors.append("TRUSTED_PROXY_CIDRS contains invalid IP networks")
        database_password = _url_password(cls.DATABASE_URL)
        redis_password = _url_password(cls.REDIS_URL) if cls.JOB_QUEUE_MODE == "rq" else None
        if _url_uses_weak_secret(cls.DATABASE_URL, {"content_ops", "postgres", "password"}):
            errors.append("production DATABASE_URL must include a high-entropy password of at least 16 characters")
        if cls.JOB_QUEUE_MODE == "rq" and _url_uses_weak_secret(
            cls.REDIS_URL, {"content_ops", "redis", "password"}
        ):
            errors.append("production REDIS_URL must include a high-entropy password of at least 16 characters")
        secrets = [cls.AUTH_PASSWORD, cls.AUTH_SECRET_KEY, database_password, redis_password]
        normalized = [secret for secret in secrets if secret]
        if len(normalized) != len(set(normalized)):
            errors.append("production authentication, signing, database, and Redis secrets must be distinct")

        if errors:
            raise ValueError("Unsafe production configuration: " + "; ".join(errors))
        return True

    @classmethod
    def validate(cls, provider: str | None = None):
        """验证配置"""
        provider = (provider or cls.LLM_PROVIDER).lower()
        if provider not in cls.get_supported_providers():
            raise ValueError(f"Unknown provider: {provider}")

        if provider == "claude" and not cls.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required for Claude provider")
        elif provider == "siliconflow" and not cls.SILICONFLOW_API_KEY:
            raise ValueError("SILICONFLOW_API_KEY is required for SiliconFlow provider")
        elif provider == "deepseek" and not cls.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek provider")
        elif provider == "moonshot" and not cls.MOONSHOT_API_KEY:
            raise ValueError("MOONSHOT_API_KEY is required for Moonshot provider")
        elif provider == "newapi":
            if not cls.NEWAPI_API_KEY:
                raise ValueError("NEWAPI_API_KEY is required for NewAPI provider")
            if not cls.NEWAPI_BASE_URL:
                raise ValueError("NEWAPI_BASE_URL is required for NewAPI provider")

        return True

    @classmethod
    def get_api_key(cls, provider: str | None = None) -> str:
        """获取指定提供商的 API Key"""
        provider = (provider or cls.LLM_PROVIDER).lower()

        if provider == "claude":
            return cls.ANTHROPIC_API_KEY
        elif provider == "siliconflow":
            return cls.SILICONFLOW_API_KEY
        elif provider == "deepseek":
            return cls.DEEPSEEK_API_KEY
        elif provider == "moonshot":
            return cls.MOONSHOT_API_KEY
        elif provider == "newapi":
            return cls.NEWAPI_API_KEY
        else:
            raise ValueError(f"Unknown provider: {provider}")

    @classmethod
    def get_model(cls, provider: str | None = None) -> str:
        """获取指定提供商的模型"""
        provider = (provider or cls.LLM_PROVIDER).lower()

        if provider == "claude":
            return cls.CLAUDE_MODEL
        elif provider == "siliconflow":
            return cls.SILICONFLOW_MODEL
        elif provider == "deepseek":
            return cls.DEEPSEEK_MODEL
        elif provider == "moonshot":
            return cls.MOONSHOT_MODEL
        elif provider == "newapi":
            return cls.NEWAPI_MODEL
        else:
            raise ValueError(f"Unknown provider: {provider}")

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        return ["claude", "siliconflow", "deepseek", "moonshot", "newapi"]

    @classmethod
    def has_provider_key(cls, provider: str) -> bool:
        provider = provider.lower()
        if provider == "claude":
            return bool(cls.ANTHROPIC_API_KEY)
        elif provider == "siliconflow":
            return bool(cls.SILICONFLOW_API_KEY)
        elif provider == "deepseek":
            return bool(cls.DEEPSEEK_API_KEY)
        elif provider == "moonshot":
            return bool(cls.MOONSHOT_API_KEY)
        elif provider == "newapi":
            return bool(cls.NEWAPI_API_KEY) and bool(cls.NEWAPI_BASE_URL)
        return False

    @classmethod
    def get_litellm_model(cls, provider: str | None = None, model: str | None = None) -> str:
        provider = (provider or cls.LLM_PROVIDER).lower()
        if model:
            if provider == "siliconflow" and not model.startswith("openai/"):
                return f"openai/{model}"
            if provider == "deepseek" and not model.startswith("deepseek/"):
                return f"deepseek/{model}"
            if provider == "moonshot" and not model.startswith("moonshot/"):
                return f"moonshot/{model}"
            # NewAPI is just an OpenAI-compatible gateway — route through litellm's
            # `openai/` provider so it forwards the call as plain /v1/chat/completions
            # against api_base, without any provider-specific schema rewrites.
            if provider == "newapi" and not model.startswith("openai/"):
                return f"openai/{model}"
            return model

        if provider == "claude":
            return cls.CLAUDE_MODEL
        elif provider == "siliconflow":
            return f"openai/{cls.SILICONFLOW_MODEL}"
        elif provider == "deepseek":
            return f"deepseek/{cls.DEEPSEEK_MODEL}"
        elif provider == "moonshot":
            return f"moonshot/{cls.MOONSHOT_MODEL}"
        elif provider == "newapi":
            return f"openai/{cls.NEWAPI_MODEL}"
        else:
            raise ValueError(f"Unknown provider: {provider}")

    @classmethod
    def get_provider_api_base(cls, provider: str) -> str | None:
        provider = provider.lower()
        if provider == "siliconflow":
            return cls.SILICONFLOW_BASE_URL
        elif provider == "deepseek":
            return cls.DEEPSEEK_BASE_URL
        elif provider == "moonshot":
            return cls.MOONSHOT_BASE_URL
        elif provider == "newapi":
            # NewAPI gateways accept both `https://host` and `https://host/v1` in admin UI,
            # but litellm's openai provider always appends `/chat/completions` to api_base.
            # Without `/v1` the request lands on the gateway's SPA root (returns HTML).
            # Normalize here so users can paste either form into NEWAPI_BASE_URL.
            base = (cls.NEWAPI_BASE_URL or "").rstrip("/")
            if not base:
                return None
            return base if base.endswith("/v1") else f"{base}/v1"
        return None

    @classmethod
    def planner_response_format(cls, provider: str) -> dict[str, str] | None:
        """Wire-level ``response_format`` for the planner, or None to use plain text.

        Returns ``{"type": "json_object"}`` for the OpenAI-compatible providers and
        ``None`` for Claude, whose API has no ``response_format`` parameter — sending
        one there is rejected outright, so the planner stays on the text path and
        relies on parse/repair instead.

        JSON *object* mode rather than a strict JSON *schema*: schema mode is only
        honoured by a subset of models behind these gateways, and an unsupported
        schema is a hard request error rather than a soft downgrade. Object mode is
        widely accepted, and its one real constraint — the response cannot be a
        top-level array — is already handled by the planner envelope unwrapping.
        """
        if not cls.PLANNER_STRUCTURED_OUTPUT_ENABLED:
            return None
        if provider.lower() in {"siliconflow", "deepseek", "moonshot", "newapi"}:
            return {"type": "json_object"}
        return None


def _is_unsafe_secret(
    value: str | None,
    *,
    minimum: int = 1,
    minimum_unique: int = 6,
) -> bool:
    secret = value or ""
    lowered = secret.lower()
    markers = ("change_me", "changeme", "replace_me", "replace-with", "example", "password")
    if (
        len(secret) < minimum
        or len(set(secret)) < minimum_unique
        or lowered in {"content_ops", "postgres", "redis"}
        or any(marker in lowered for marker in markers)
    ):
        return True
    frequencies = Counter(secret)
    entropy = -sum((count / len(secret)) * math.log2(count / len(secret)) for count in frequencies.values())
    return entropy < 2.5


def _url_password(value: str) -> str | None:
    try:
        raw_password = urlsplit(value).password
        return unquote(raw_password) if raw_password else None
    except ValueError:
        return None


def _url_uses_weak_secret(value: str, examples: set[str]) -> bool:
    password = _url_password(value)
    return _is_unsafe_secret(password, minimum=16, minimum_unique=10) or bool(
        password and password.lower() in examples
    )


config = Config()
