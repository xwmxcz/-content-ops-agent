"""OpenAI 兼容 API 客户端（支持 DeepSeek、Moonshot 等）"""
import requests
from src.llm.base import BaseLLMClient


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容 API 客户端"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        provider_name: str = "OpenAI Compatible",
    ):
        """
        初始化

        Args:
            api_key: API Key
            model: 模型名称
            base_url: API 基础 URL
            provider_name: 提供商名称
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.provider_name = provider_name

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """生成内容"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=60,
        )

        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def get_model_name(self) -> str:
        """获取模型名称"""
        return f"{self.provider_name} ({self.model})"

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """估算成本（需要根据具体提供商配置）"""
        # 默认返回 0，子类可以覆盖
        return 0.0


class DeepSeekClient(OpenAICompatibleClient):
    """DeepSeek API 客户端"""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://api.deepseek.com/v1",
            provider_name="DeepSeek",
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        DeepSeek 定价:
        - Input: ¥1 / 1M tokens
        - Output: ¥2 / 1M tokens
        """
        input_cost_cny = (input_tokens / 1_000_000) * 1
        output_cost_cny = (output_tokens / 1_000_000) * 2
        cost_usd = (input_cost_cny + output_cost_cny) / 7
        return cost_usd


class MoonshotClient(OpenAICompatibleClient):
    """Moonshot (Kimi) API 客户端"""

    def __init__(self, api_key: str, model: str = "moonshot-v1-8k"):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://api.moonshot.cn/v1",
            provider_name="Moonshot",
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Moonshot 定价（参考）:
        - 8K: ¥12 / 1M tokens
        """
        total_tokens = input_tokens + output_tokens
        cost_cny = (total_tokens / 1_000_000) * 12
        cost_usd = cost_cny / 7
        return cost_usd
