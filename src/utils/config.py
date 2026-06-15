import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """应用配置"""

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

    # Authentication
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
    AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
    AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
    AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "")
    AUTH_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440"))

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/content_ops.db")
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT_SECONDS = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))

    # Background job settings
    JOB_QUEUE_MODE = os.getenv("JOB_QUEUE_MODE", "background").lower()  # background or rq
    JOB_QUEUE_NAME = os.getenv("JOB_QUEUE_NAME", "content_ops")
    JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "300"))
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MAX_PROVIDER_INFLIGHT_JOBS = int(os.getenv("MAX_PROVIDER_INFLIGHT_JOBS", "8"))

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
    # Memory curator: when a thread is closed, an auxiliary LLM proposes
    # add/replace/remove operations on MEMORY.md / USER.md and applies them.
    MEMORY_CURATOR_ENABLED = os.getenv("MEMORY_CURATOR_ENABLED", "true").lower() == "true"
    MEMORY_CURATOR_MIN_MESSAGES = int(os.getenv("MEMORY_CURATOR_MIN_MESSAGES", "4"))
    MEMORY_CURATOR_MAX_ACTIONS = int(os.getenv("MEMORY_CURATOR_MAX_ACTIONS", "6"))

    # App Settings
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    API_RELOAD = os.getenv("API_RELOAD", "False").lower() == "true"
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

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


config = Config()
