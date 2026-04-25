"""硅基流动 API 客户端"""
import requests
import time
from src.llm.base import BaseLLMClient


class SiliconFlowClient(BaseLLMClient):
    """硅基流动 API 客户端"""

    def __init__(
        self,
        api_key: str,
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        base_url: str = "https://api.siliconflow.cn/v1",
        timeout: int = 120,
        max_retries: int = 3,
    ):
        """
        初始化

        Args:
            api_key: 硅基流动 API Key
            model: 模型名称
            base_url: API 基础 URL
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """生成内容（带重试机制）"""
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

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=self.timeout,
                )

                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]

            except requests.exceptions.Timeout as e:
                last_error = e
                wait_time = (attempt + 1) * 5  # 递增等待时间
                print(f"请求超时，{wait_time}秒后重试 ({attempt + 1}/{self.max_retries})...")
                time.sleep(wait_time)
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    print(f"请求失败: {e}，重试中...")
                    time.sleep(2)

        raise ConnectionError(f"API 请求失败，已重试 {self.max_retries} 次: {last_error}")

    def get_model_name(self) -> str:
        """获取模型名称"""
        return f"SiliconFlow ({self.model})"

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        估算成本

        硅基流动定价（参考，实际以官网为准）:
        Qwen2.5-7B: ¥0.35 / 1M tokens (约 $0.05)
        """
        total_tokens = input_tokens + output_tokens
        # 假设统一定价 ¥0.35/1M tokens，汇率 1:7
        cost_cny = (total_tokens / 1_000_000) * 0.35
        cost_usd = cost_cny / 7
        return cost_usd
