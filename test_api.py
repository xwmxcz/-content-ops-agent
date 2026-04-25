"""测试 SiliconFlow API 连接"""
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from src.llm.siliconflow_client import SiliconFlowClient
from src.utils import config

print('Testing SiliconFlow API...')
print(f'Model: {config.SILICONFLOW_MODEL}')
print(f'Timeout: 120s')
print()

client = SiliconFlowClient(
    api_key=config.SILICONFLOW_API_KEY,
    model=config.SILICONFLOW_MODEL,
    timeout=120
)

try:
    result = client.generate(
        system_prompt='你是一个助手',
        user_prompt='用一句话介绍自己',
        max_tokens=100
    )
    print('✅ Success!')
    print(f'Response: {result}')
except Exception as e:
    print(f'❌ Error: {e}')
