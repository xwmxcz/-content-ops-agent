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

    # Model Settings
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    MOONSHOT_MODEL = os.getenv("MOONSHOT_MODEL", "moonshot-v1-8k")

    # LiteLLM / OpenAI-compatible endpoint settings
    SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    MOONSHOT_BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")

    # Generation Settings
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/content_ops.db")

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

        if provider == "claude" and not cls.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required for Claude provider")
        elif provider == "siliconflow" and not cls.SILICONFLOW_API_KEY:
            raise ValueError("SILICONFLOW_API_KEY is required for SiliconFlow provider")
        elif provider == "deepseek" and not cls.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek provider")
        elif provider == "moonshot" and not cls.MOONSHOT_API_KEY:
            raise ValueError("MOONSHOT_API_KEY is required for Moonshot provider")

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
        else:
            raise ValueError(f"Unknown provider: {provider}")

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        return ["claude", "siliconflow", "deepseek", "moonshot"]

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
            return model

        if provider == "claude":
            return cls.CLAUDE_MODEL
        elif provider == "siliconflow":
            return f"openai/{cls.SILICONFLOW_MODEL}"
        elif provider == "deepseek":
            return f"deepseek/{cls.DEEPSEEK_MODEL}"
        elif provider == "moonshot":
            return f"moonshot/{cls.MOONSHOT_MODEL}"
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
        return None


config = Config()
