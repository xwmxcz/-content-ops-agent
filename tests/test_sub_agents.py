from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from src.api.services.sub_agents import SUB_AGENTS, SubAgentRunner
from src.storage import ContentStore


@pytest.fixture
def store(tmp_path: Path):
    db_path = tmp_path / "sub_agents.db"
    s = ContentStore(db_path=str(db_path))
    yield s
    s.engine.dispose()


class EmptyToolThenNoTextModel:
    def __init__(self):
        self.calls = 0
        self.messages = []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_history",
                        "args": {"query": "河北徒步", "limit": 10},
                        "id": "call_search_history",
                    },
                    {
                        "name": "list_recent_contents",
                        "args": {"limit": 10},
                        "id": "call_recent",
                    },
                ],
            )
        return AIMessage(content="")


class EmptyToolThenSummaryModel(EmptyToolThenNoTextModel):
    async def ainvoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_history",
                        "args": {"query": "河北徒步", "limit": 10},
                        "id": "call_search_history",
                    },
                ],
            )
        return AIMessage(content="调研总结：工具没有找到历史素材，但可以从目的地类型和出行半径切入。")


class EmptyToolThenSynthesisModel(EmptyToolThenNoTextModel):
    async def ainvoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_history",
                        "args": {"query": "河北徒步", "limit": 10},
                        "id": "call_search_history",
                    },
                    {
                        "name": "list_recent_contents",
                        "args": {"limit": 10},
                        "id": "call_recent",
                    },
                ],
            )
        if self.calls == 2:
            return AIMessage(content="")
        return AIMessage(content="真实总结：工具没有检索到历史素材，写作时需要把结论标注为待外部资料补充。")


class EmptyToolThenPseudoToolCallModel(EmptyToolThenSynthesisModel):
    async def ainvoke(self, messages):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "web_search",
                        "args": {"query": "河北徒步", "limit": 10},
                        "id": "call_web",
                    },
                ],
            )
        if self.calls == 2:
            return AIMessage(content="")
        return AIMessage(content="<tool_call>web_search<arg_key>query</arg_key></tool_call>")


@pytest.mark.asyncio
async def test_tool_agent_synthesizes_summary_when_tools_return_empty_and_model_has_no_text(store):
    model = EmptyToolThenSynthesisModel()
    runner = SubAgentRunner(store=store, model_factory=lambda *args: model)
    tool_events = []

    async def sink(event_type, payload):
        if event_type == "tool_call_result":
            tool_events.append(payload)

    text, _, _, _, _ = await runner.run(
        SUB_AGENTS["researcher"],
        user_prompt="Gather information about popular weekend hiking destinations in Hebei province",
        provider="deepseek",
        model="deepseek-v4-flash",
        tool_sink=sink,
    )

    assert text == "真实总结：工具没有检索到历史素材，写作时需要把结论标注为待外部资料补充。"
    assert model.calls == 3
    synthesis_system = model.messages[2][0].content
    assert "Tools are NOT available" in synthesis_system
    assert "You have these tools available" not in synthesis_system
    assert [event["preview"] for event in tool_events] == ["无结果", "无结果"]


@pytest.mark.asyncio
async def test_tool_agent_reports_technical_no_output_if_synthesis_is_empty(store):
    model = EmptyToolThenNoTextModel()
    runner = SubAgentRunner(store=store, model_factory=lambda *args: model)
    tool_events = []

    async def sink(event_type, payload):
        if event_type == "tool_call_result":
            tool_events.append(payload)

    text, _, _, _, _ = await runner.run(
        SUB_AGENTS["researcher"],
        user_prompt="Gather information about popular weekend hiking destinations in Hebei province",
        provider="deepseek",
        model="deepseek-v4-flash",
        tool_sink=sink,
    )

    assert "模型在工具调用后没有返回文本" in text
    assert "未返回结果" in text
    assert "建议下一步" not in text
    assert [event["preview"] for event in tool_events] == ["无结果", "无结果"]


@pytest.mark.asyncio
async def test_tool_agent_rejects_pseudo_tool_call_as_final_text(store):
    model = EmptyToolThenPseudoToolCallModel()
    runner = SubAgentRunner(store=store, model_factory=lambda *args: model)

    text, _, _, _, _ = await runner.run(
        SUB_AGENTS["researcher"],
        user_prompt="Gather information about popular weekend hiking destinations in Hebei province",
        provider="deepseek",
        model="deepseek-v4-flash",
    )

    assert "<tool_call>" not in text
    assert "模型在工具调用后没有返回文本" in text


def test_tool_preview_reports_structured_search_failure():
    preview = SubAgentRunner._tool_preview(
        '{"error": "DuckDuckGo returned an anti-bot challenge instead of search results.", "results": []}'
    )

    assert preview == "搜索失败：DuckDuckGo returned an anti-bot challenge instead of search results."


@pytest.mark.asyncio
async def test_tool_agent_keeps_model_summary_when_present(store):
    model = EmptyToolThenSummaryModel()
    runner = SubAgentRunner(store=store, model_factory=lambda *args: model)

    text, _, _, _, _ = await runner.run(
        SUB_AGENTS["researcher"],
        user_prompt="Gather information about popular weekend hiking destinations in Hebei province",
        provider="deepseek",
        model="deepseek-v4-flash",
    )

    assert text == "调研总结：工具没有找到历史素材，但可以从目的地类型和出行半径切入。"
