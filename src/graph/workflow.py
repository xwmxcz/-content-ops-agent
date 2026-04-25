"""Content Ops Agent 工作流定义"""

from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from .state import ContentOpsState
from src.utils import config
from src.tools.content_tools import (
    generate_content,
    refine_content,
    rewrite_with_style,
    generate_title_options,
    optimize_seo,
    view_content,
    list_recent_contents
)
from src.tools.calendar_tools import (
    add_to_calendar,
    view_calendar,
    batch_generate_week,
    get_content_stats
)


# 系统提示词
AGENT_SYSTEM_PROMPT = """你是 Content Ops Agent，一个智能内容运营助手。你的目标是帮助用户创作、优化和管理内容。

## 你的能力

### 📝 内容生成
- `generate_content`: 生成新内容（小红书、微博、博客、视频脚本等）
- `generate_title_options`: 生成多个标题供选择
- `view_content`: 查看内容详情
- `list_recent_contents`: 列出最近的内容

### ✨ 内容优化
- `refine_content`: 按指令改写内容
- `rewrite_with_style`: 切换风格重写
- `optimize_seo`: SEO 关键词优化建议

### 📅 内容日历
- `add_to_calendar`: 将内容加入发布日历
- `view_calendar`: 查看发布日历
- `batch_generate_week`: 批量生成一周内容
- `get_content_stats`: 查看内容统计

## 交互原则

1. **理解意图**: 准确理解用户想要做什么
2. **选择工具**: 选择最合适的工具来完成任务
3. **友好反馈**: 用清晰、友好的方式呈现结果
4. **主动建议**: 在适当时候提供有价值的建议

## 示例交互

用户: "帮我写一篇小红书文案，主题是如何提高工作效率"
→ 使用 generate_content 生成内容

用户: "这个文案太正式了，换一种更轻松的风格"
→ 使用 rewrite_with_style 或 refine_content 改写

记住：你是用户内容运营的得力助手！
"""


def create_content_agent():
    """创建 Content Ops Agent"""
    tools = [
        generate_content,
        generate_title_options,
        view_content,
        list_recent_contents,
        refine_content,
        rewrite_with_style,
        optimize_seo,
        add_to_calendar,
        view_calendar,
        batch_generate_week,
        get_content_stats,
    ]

    try:
        from langchain_anthropic import ChatAnthropic
        model = ChatAnthropic(
            api_key=config.get_api_key(),
            model=config.get_model(),
            temperature=config.TEMPERATURE
        )
    except ImportError:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            api_key=config.get_api_key(),
            base_url=config.BASE_URL if hasattr(config, 'BASE_URL') else None,
            model=config.get_model(),
            temperature=config.TEMPERATURE
        )

    model_with_tools = model.bind_tools(tools)
    tool_node = ToolNode(tools)

    def agent_node(state: ContentOpsState) -> dict:
        messages = state["messages"]
        if len(messages) == 1:
            messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)] + list(messages)
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: ContentOpsState) -> Literal["tools", "end"]:
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "end"

    workflow = StateGraph(ContentOpsState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END}
    )
    workflow.add_edge("tools", "agent")

    checkpointer = MemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    return app


class ContentOpsAgent:
    """Content Ops Agent 封装类"""

    def __init__(self):
        self.app = create_content_agent()
        self.thread_id = "default"

    def chat(self, message: str, thread_id: str = None) -> str:
        if thread_id:
            self.thread_id = thread_id
        config_dict = {"configurable": {"thread_id": self.thread_id}}
        result = self.app.invoke(
            {"messages": [HumanMessage(content=message)]},
            config=config_dict
        )
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage):
                return msg.content
        return "抱歉，我无法处理这个请求。"

    def stream(self, message: str, thread_id: str = None):
        if thread_id:
            self.thread_id = thread_id
        config_dict = {"configurable": {"thread_id": self.thread_id}}
        for event in self.app.stream(
            {"messages": [HumanMessage(content=message)]},
            config=config_dict,
            stream_mode="updates"
        ):
            yield event

    def reset(self):
        self.thread_id = f"session_{__import__('uuid').uuid4().hex[:8]}"
