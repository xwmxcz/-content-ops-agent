# Content Ops Agent

智能内容运营 Agent - 自动化内容创作、优化和发布

## 功能特性

- 🎯 多平台内容生成（小红书、微博、博客、视频脚本）
- 🤖 多 LLM API 支持（Claude、硅基流动、DeepSeek、Moonshot）
- ✨ 智能文案优化和改写
- 📦 批量内容生成
- 🎨 内容模板系统
- 💰 成本优化（最多节省 96% API 费用）

## 🌟 多 API 支持

支持 4 个 LLM 提供商，灵活选择：

| 提供商 | 优势 | 成本 | 适用场景 |
|--------|------|------|---------|
| Claude | 质量最高 | $$ | 重要内容 |
| 硅基流动 | 便宜快速 | $ | 批量生成 |
| DeepSeek | 性价比高 | $ | 日常使用 |
| Moonshot | 长上下文 | $$ | 长文章 |

详见 [MULTI_API_GUIDE.md](MULTI_API_GUIDE.md)

## 快速开始

```bash
# 1. 安装依赖
conda activate only
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件：
# - 设置 LLM_PROVIDER (claude/siliconflow/deepseek/moonshot)
# - 添加对应的 API Key

# 3. 运行旧版 CLI
python run.py

# 4. 运行新版 FastAPI 后端
python server.py

# 5. 运行新版 Vue 前端
cd frontend
npm install
npm run dev

# 6. 测试多 API
python examples/multi_api_demo.py
```

## 技术栈

- Python 3.10+
- 多 LLM API (Claude, SiliconFlow, DeepSeek, Moonshot)
- 抽象接口设计 + 工厂模式
- LangGraph
- FastAPI REST API
- Vue 3 + Vite + Element Plus
- Streamlit（迁移期保留）

## 项目结构

```
content-ops-agent/
├── src/
│   ├── models/          # 数据模型
│   ├── api/             # FastAPI 后端接口
│   ├── tools/           # 内容生成工具
│   ├── graph/           # LangGraph 工作流
│   ├── utils/           # 工具函数
│   └── main.py          # 主程序
├── frontend/            # Vue 3 前端
├── examples/            # 示例代码
├── tests/               # 测试
├── data/                # 数据存储
├── run.py               # 旧版 CLI 启动脚本
├── server.py            # 新版 API 启动脚本
└── requirements.txt     # Python 依赖
```

## 开发计划

详见 [PROJECT_PLAN.md](PROJECT_PLAN.md)
