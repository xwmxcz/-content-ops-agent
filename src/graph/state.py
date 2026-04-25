"""Content Ops Agent 状态定义"""

from typing import TypedDict, Annotated, Sequence, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ContentOpsState(TypedDict):
    """
    Content Ops Agent 的状态定义
    """

    # 消息历史
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # 用户意图: generate/refine/calendar/analytics/other
    user_intent: Optional[str]

    # 当前正在打磨的内容草稿
    current_content: Optional[dict]

    # 当前关联的数据库内容 ID
    content_id: Optional[int]

    # 工具执行结果
    tool_results: Optional[list[dict]]

    # 错误信息
    error: Optional[str]


def get_initial_state() -> ContentOpsState:
    """获取初始状态"""
    return ContentOpsState(
        messages=[],
        user_intent=None,
        current_content=None,
        content_id=None,
        tool_results=None,
        error=None
    )
