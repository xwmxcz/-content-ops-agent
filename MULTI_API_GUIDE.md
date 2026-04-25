# 多 API 支持指南

## 🎯 支持的 LLM 提供商

Content Ops Agent 现在支持多个 LLM API 提供商，你可以根据需求选择：

### 1. Claude (Anthropic) 🌟
- **优势**: 质量最高，理解能力强
- **定价**: Input $3/1M, Output $15/1M tokens
- **适用**: 重要内容、高质量要求
- **模型**: `claude-3-5-sonnet-20241022`

### 2. 硅基流动 (SiliconFlow) 💰
- **优势**: 价格便宜，国内访问快
- **定价**: 约 ¥0.35/1M tokens
- **适用**: 批量生成、成本敏感场景
- **模型**: `Qwen/Qwen2.5-7B-Instruct`
- **官网**: https://siliconflow.cn/

### 3. DeepSeek 🚀
- **优势**: 性价比高，中文友好
- **定价**: Input ¥1/1M, Output ¥2/1M tokens
- **适用**: 日常内容生成
- **模型**: `deepseek-chat`
- **官网**: https://www.deepseek.com/

### 4. Moonshot (Kimi) 🌙
- **优势**: 长上下文，中文优秀
- **定价**: 约 ¥12/1M tokens
- **适用**: 长文章、复杂内容
- **模型**: `moonshot-v1-8k`
- **官网**: https://www.moonshot.cn/

---

## 🔧 配置方法

### 1. 编辑 .env 文件

```bash
# 选择提供商
LLM_PROVIDER=siliconflow  # 可选: claude, siliconflow, deepseek, moonshot

# 配置对应的 API Key（只需配置你使用的）
SILICONFLOW_API_KEY=sk-your-key-here
DEEPSEEK_API_KEY=sk-your-key-here
MOONSHOT_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=sk-your-key-here

# 可选：自定义模型
# SILICONFLOW_MODEL=Qwen/Qwen2.5-72B-Instruct
```

### 2. 在代码中使用

```python
from src.tools import ContentGenerator

# 方式 1: 使用 .env 配置的默认提供商
generator = ContentGenerator()

# 方式 2: 指定提供商
generator = ContentGenerator(provider="siliconflow")

# 方式 3: 完全自定义
generator = ContentGenerator(
    provider="deepseek",
    api_key="your-key",
    model="deepseek-chat"
)
```

---

## 💡 使用建议

### 成本优化策略

1. **批量生成**: 使用便宜的 API
   ```python
   # 使用硅基流动批量生成
   generator = ContentGenerator(provider="siliconflow")
   results = generator.batch_generate(requests)
   ```

2. **重要内容**: 使用高质量 API
   ```python
   # 使用 Claude 生成重要内容
   generator = ContentGenerator(provider="claude")
   result = generator.generate(important_request)
   ```

3. **混合使用**: 初稿 + 优化
   ```python
   # 用便宜的 API 生成初稿
   draft_gen = ContentGenerator(provider="deepseek")
   draft = draft_gen.generate(request)
   
   # 用高质量 API 优化
   polish_gen = ContentGenerator(provider="claude")
   final = polish_gen.generate(polish_request)
   ```

### 成本对比（生成 1000 字内容）

| 提供商 | 单次成本 | 100 次成本 | 1000 次成本 |
|--------|---------|-----------|------------|
| Claude | $0.027 | $2.70 | $27.00 |
| SiliconFlow | $0.001 | $0.10 | $1.00 |
| DeepSeek | $0.002 | $0.20 | $2.00 |
| Moonshot | $0.017 | $1.70 | $17.00 |

💡 **建议**: 日常使用 SiliconFlow/DeepSeek，重要内容用 Claude

---

## 🧪 测试不同提供商

运行对比示例：

```bash
python examples/multi_api_demo.py
```

功能：
1. 查看支持的提供商
2. 对比生成效果
3. 成本估算

---

## 🔑 获取 API Key

### 硅基流动
1. 访问 https://siliconflow.cn/
2. 注册账号
3. 在控制台创建 API Key
4. 新用户通常有免费额度

### DeepSeek
1. 访问 https://platform.deepseek.com/
2. 注册账号
3. 获取 API Key
4. 充值使用（价格便宜）

### Moonshot
1. 访问 https://platform.moonshot.cn/
2. 注册账号
3. 创建 API Key
4. 新用户有免费额度

### Claude
1. 访问 https://console.anthropic.com/
2. 注册账号
3. 添加支付方式
4. 创建 API Key

---

## 🎯 最佳实践

### 1. 开发阶段
- 使用便宜的 API 快速迭代
- 测试 Prompt 效果

### 2. 生产阶段
- 根据内容重要性选择 API
- 监控成本和质量
- 设置预算上限

### 3. 商业化阶段
- 基础服务用便宜 API（保证利润）
- 高级服务用优质 API（保证质量）
- 提供 API 选择权给客户

---

## ⚠️ 注意事项

1. **API Key 安全**
   - 不要提交到 Git
   - 使用环境变量
   - 定期轮换

2. **成本控制**
   - 设置 max_tokens 限制
   - 监控使用量
   - 使用缓存机制

3. **质量保证**
   - 不同 API 效果可能不同
   - 重要内容建议人工审核
   - 收集用户反馈

4. **国内访问**
   - Claude 需要代理
   - 国内 API 访问更快
   - 考虑网络稳定性

---

## 🚀 下一步

1. 测试不同提供商的效果
2. 根据业务需求选择合适的 API
3. 优化成本和质量的平衡
4. 实现智能路由（自动选择最优 API）

有问题随时查看文档或提问！
