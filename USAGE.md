# Content Ops Agent - 使用指南

## 快速开始

### 1. 安装依赖

```bash
cd content-ops-agent
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，添加你的 Anthropic API Key
# ANTHROPIC_API_KEY=your_api_key_here
```

### 3. 运行示例

```bash
# 运行基础示例
python run.py

# 运行交互式示例
python examples/quick_start.py
```

## 使用示例

### 生成小红书文案

```python
from src.tools import ContentGenerator
from src.models import ContentRequest, ContentType, ContentStyle

generator = ContentGenerator()

request = ContentRequest(
    topic="如何提高工作效率",
    content_type=ContentType.XIAOHONGSHU,
    style=ContentStyle.CASUAL,
    keywords=["效率", "时间管理"],
    length="medium"
)

result = generator.generate(request)
print(result.title)
print(result.content)
print(result.tags)
```

### 批量生成内容

```python
requests = [
    ContentRequest(topic="主题1", content_type=ContentType.XIAOHONGSHU),
    ContentRequest(topic="主题2", content_type=ContentType.BLOG),
    ContentRequest(topic="主题3", content_type=ContentType.WEIBO),
]

results = generator.batch_generate(requests)
```

## 支持的内容类型

- `XIAOHONGSHU` - 小红书文案
- `WEIBO` - 微博文案
- `BLOG` - 博客文章
- `VIDEO_SCRIPT` - 视频脚本
- `TWITTER` - Twitter 文案

## 支持的风格

- `PROFESSIONAL` - 专业风格
- `CASUAL` - 轻松风格
- `MARKETING` - 营销风格
- `STORYTELLING` - 故事性风格

## 下一步

1. 尝试不同的内容类型和风格
2. 调整 Prompt 模板以适应你的需求
3. 添加更多平台支持
4. 集成到你的工作流中

## 获取 API Key

访问 [Anthropic Console](https://console.anthropic.com/) 获取 API Key。
