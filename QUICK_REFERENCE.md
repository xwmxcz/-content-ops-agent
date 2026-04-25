# 🚀 快速参考 - 多 API 使用

## 一分钟上手

### 1. 获取 API Key（推荐硅基流动）

访问 https://siliconflow.cn/ 注册并获取免费 API Key

### 2. 配置

```bash
# 编辑 .env
LLM_PROVIDER=siliconflow
SILICONFLOW_API_KEY=sk-your-key-here
```

### 3. 运行

```bash
python run.py
```

---

## 常用命令

```bash
# 测试配置
python test_setup.py

# 基础示例
python run.py

# 交互式示例
python examples/quick_start.py

# 多 API 对比
python examples/multi_api_demo.py
```

---

## 代码示例

### 使用默认配置
```python
from src.tools import ContentGenerator
from src.models import ContentRequest, ContentType, ContentStyle

generator = ContentGenerator()
request = ContentRequest(
    topic="如何提高工作效率",
    content_type=ContentType.XIAOHONGSHU,
    style=ContentStyle.CASUAL
)
result = generator.generate(request)
```

### 指定提供商
```python
# 便宜快速
generator = ContentGenerator(provider="siliconflow")

# 高质量
generator = ContentGenerator(provider="claude")

# 性价比
generator = ContentGenerator(provider="deepseek")
```

### 批量生成
```python
requests = [
    ContentRequest(topic="主题1", content_type=ContentType.XIAOHONGSHU),
    ContentRequest(topic="主题2", content_type=ContentType.BLOG),
]
results = generator.batch_generate(requests)
```

---

## API 选择建议

| 场景 | 推荐 API | 原因 |
|------|---------|------|
| 测试开发 | SiliconFlow | 便宜，快速迭代 |
| 批量生成 | SiliconFlow/DeepSeek | 成本低 |
| 重要内容 | Claude | 质量最高 |
| 长文章 | Moonshot | 长上下文 |
| 日常使用 | DeepSeek | 性价比高 |

---

## 成本速查表

生成 1000 字内容：

- **SiliconFlow**: $0.001 ⭐ 最便宜
- **DeepSeek**: $0.002 ⭐ 性价比
- **Moonshot**: $0.017
- **Claude**: $0.027 ⭐ 最高质量

---

## 常见问题

### Q: 如何切换 API？
A: 修改 .env 中的 `LLM_PROVIDER` 即可

### Q: 哪个 API 最便宜？
A: 硅基流动（SiliconFlow），比 Claude 便宜 27 倍

### Q: 质量有差别吗？
A: Claude 质量最高，但其他 API 日常使用足够

### Q: 可以混合使用吗？
A: 可以！代码中指定不同的 provider 即可

### Q: 如何获取 API Key？
A: 查看 MULTI_API_GUIDE.md 中的详细说明

---

## 获取 API Key

### 硅基流动（推荐）
- 网址: https://siliconflow.cn/
- 特点: 新用户有免费额度
- 价格: 最便宜

### DeepSeek
- 网址: https://platform.deepseek.com/
- 特点: 性价比高
- 价格: 很便宜

### Moonshot
- 网址: https://platform.moonshot.cn/
- 特点: 长上下文
- 价格: 中等

### Claude
- 网址: https://console.anthropic.com/
- 特点: 质量最高
- 价格: 较贵

---

## 下一步

1. ✅ 获取 API Key
2. ✅ 配置 .env
3. ✅ 运行测试
4. ✅ 生成内容
5. ✅ 开始赚钱！

详细文档：
- [MULTI_API_GUIDE.md](MULTI_API_GUIDE.md) - 完整指南
- [MULTI_API_SUMMARY.md](MULTI_API_SUMMARY.md) - 更新总结
- [PROJECT_PLAN.md](PROJECT_PLAN.md) - 项目计划
