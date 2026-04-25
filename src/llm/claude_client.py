"""Claude API 客户端"""
from anthropic import Anthropic
from src.llm.base import BaseLLMClient


class ClaudeClient(BaseLLMClient):
    """Claude API 客户端"""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        初始化

        Args:
            api_key: Anthropic API Key
            model: 模型名称
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """生成内容"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def get_model_name(self) -> str:
        """获取模型名称"""
        return f"Claude ({self.model})"

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        估算成本

        Claude 3.5 Sonnet 定价（2024）:
        - Input: $3 / 1M tokens
        - Output: $15 / 1M tokens
        """
        input_cost = (input_tokens / 1_000_000) * 3
        output_cost = (output_tokens / 1_000_000) * 15
        return input_cost + output_cost
