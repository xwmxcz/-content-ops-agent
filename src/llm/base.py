"""LLM 客户端抽象接口"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseLLMClient(ABC):
    """LLM 客户端基类"""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        生成内容

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            生成的文本内容
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """获取模型名称"""
        pass

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        估算成本（美元）

        Args:
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数

        Returns:
            成本（美元）
        """
        pass
