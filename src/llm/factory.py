"""LLM 客户端工厂"""
from typing import Optional
from src.llm.base import BaseLLMClient
from src.llm.claude_client import ClaudeClient
from src.llm.siliconflow_client import SiliconFlowClient
from src.llm.openai_compatible import DeepSeekClient, MoonshotClient


class LLMFactory:
    """LLM 客户端工厂"""

    @staticmethod
    def create_client(
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        **kwargs
    ) -> BaseLLMClient:
        """
        创建 LLM 客户端

        Args:
            provider: 提供商名称 (claude, siliconflow, deepseek, moonshot)
            api_key: API Key
            model: 模型名称（可选，使用默认值）
            **kwargs: 其他参数

        Returns:
            LLM 客户端实例

        Raises:
            ValueError: 不支持的提供商
        """
        provider = provider.lower()

        if provider == "claude":
            model = model or "claude-3-5-sonnet-20241022"
            return ClaudeClient(api_key=api_key, model=model)

        elif provider == "siliconflow":
            model = model or "Qwen/Qwen2.5-7B-Instruct"
            return SiliconFlowClient(api_key=api_key, model=model)

        elif provider == "deepseek":
            model = model or "deepseek-chat"
            return DeepSeekClient(api_key=api_key, model=model)

        elif provider == "moonshot":
            model = model or "moonshot-v1-8k"
            return MoonshotClient(api_key=api_key, model=model)

        else:
            raise ValueError(
                f"Unsupported provider: {provider}. "
                f"Supported: claude, siliconflow, deepseek, moonshot"
            )

    @staticmethod
    def get_supported_providers() -> list[str]:
        """获取支持的提供商列表"""
        return ["claude", "siliconflow", "deepseek", "moonshot"]
