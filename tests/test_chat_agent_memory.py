"""Tests for the chat agent's file-based memory integration."""
from __future__ import annotations

import json
import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.api.schemas.agent import ChatRequest
from src.api.services.chat_agent import ChatAgentService, _FROZEN_PROMPTS
from src.storage import ContentStore
from src.storage.file_memory import AGENT, FileMemory, USER


# ─── Fakes mirroring test_api_contract patterns ────────────────────────────


class FakeLLMClient:
    async def generate_from_prompts(self, **kw):
        return "stub"

    async def generate(self, **kw):
        return "stub"


class CapturingChatModel:
    """Records the messages it sees and returns canned AI replies."""

    def __init__(self, factory):
        self.factory = factory

    def bind_tools(self, tools):
        self.factory.tools = tools
        return self

    async def ainvoke(self, messages: list[BaseMessage]):
        self.factory.captured_runs.append(list(messages))
        # Optional tool spec drives one tool call then a final reply
        spec = self.factory.next_tool_call
        already_called = any(isinstance(m, ToolMessage) for m in messages)
        if spec and not already_called:
            return AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": spec["name"], "args": spec["args"]}],
            )
        return AIMessage(content="final reply")


class CapturingChatFactory:
    def __init__(self):
        self.captured_runs: list[list[BaseMessage]] = []
        self.tools = []
        self.next_tool_call: dict | None = None

    def __call__(self, provider, model, temperature, max_tokens):
        return CapturingChatModel(self)

    def agent_runs(self) -> list[list[BaseMessage]]:
        """Drop planner/intent calls and keep only main agent turns."""
        out = []
        for messages in self.captured_runs:
            if not messages or not isinstance(messages[0], SystemMessage):
                continue
            if messages[0].content.startswith("You are a planner."):
                continue
            if messages[0].content.startswith("You are an intent recognizer"):
                continue
            out.append(messages)
        return out


@pytest.fixture(autouse=True)
def _clear_frozen_cache():
    _FROZEN_PROMPTS.clear()
    yield
    _FROZEN_PROMPTS.clear()


@pytest.fixture
def store():
    return ContentStore(database_url="sqlite:///:memory:")


@pytest.fixture
def file_memory(tmp_path):
    fm = FileMemory(tmp_path / "memory", memory_limit=500, user_limit=300)
    fm.save(AGENT, "项目品牌口径:简洁口语化中文")
    fm.save(USER, "用户偏好简洁、不喜欢 emoji")
    return fm


@pytest.fixture
def service(store, file_memory):
    factory = CapturingChatFactory()
    svc = ChatAgentService(
        store=store,
        llm=FakeLLMClient(),
        model_factory=factory,
        file_memory=file_memory,
        context_engine=None,
    )
    return svc, factory


# ─── System prompt freezing ────────────────────────────────────────────────


class TestFrozenSystemPrompt:
    @pytest.mark.asyncio
    async def test_two_turns_share_same_frozen_prefix(self, service):
        svc, factory = service
        # Turn 1
        await svc.chat(ChatRequest(message="hi", thread_id="t1"))
        # Turn 2 — different user message
        await svc.chat(ChatRequest(message="另一个问题", thread_id="t1"))
        runs = factory.agent_runs()
        assert len(runs) >= 2
        run1_sys = runs[0][0].content
        run2_sys = runs[1][0].content
        assert run1_sys == run2_sys
        assert "项目品牌口径" in run1_sys
        assert "用户偏好简洁" in run1_sys

    @pytest.mark.asyncio
    async def test_memory_write_does_not_affect_current_session(self, service, file_memory):
        svc, factory = service
        await svc.chat(ChatRequest(message="hi", thread_id="t1"))
        file_memory.add(USER, "新增偏好:不爱写很长")
        await svc.chat(ChatRequest(message="next", thread_id="t1"))
        runs = factory.agent_runs()
        run1_sys = runs[0][0].content
        run2_sys = runs[1][0].content
        assert run1_sys == run2_sys
        assert "新增偏好" not in run2_sys

    @pytest.mark.asyncio
    async def test_new_thread_picks_up_latest_memory(self, service, file_memory):
        svc, factory = service
        await svc.chat(ChatRequest(message="hi", thread_id="t1"))
        file_memory.add(USER, "新增偏好:不爱写很长")
        await svc.chat(ChatRequest(message="hi", thread_id="t2"))
        runs = factory.agent_runs()
        run1_sys = runs[0][0].content
        run2_sys = runs[-1][0].content
        assert "新增偏好" in run2_sys
        assert "新增偏好" not in run1_sys

    @pytest.mark.asyncio
    async def test_invalidate_frozen_drops_cache(self, service, file_memory):
        svc, factory = service
        await svc.chat(ChatRequest(message="hi", thread_id="t1"))
        file_memory.add(AGENT, "新规则:always quote dates as YYYY-MM-DD")
        ChatAgentService.invalidate_frozen("t1")
        await svc.chat(ChatRequest(message="hi", thread_id="t1"))
        run2_sys = factory.agent_runs()[-1][0].content
        assert "新规则" in run2_sys


# ─── New tool surface ──────────────────────────────────────────────────────


class TestMemoryTools:
    def test_tool_names_swapped(self, service):
        svc, _ = service
        tools = svc._build_tools("claude", "m", 0.7, 1024)
        names = {t.name for t in tools}
        assert {"memory_add", "memory_replace", "memory_remove", "session_search"} <= names
        assert "remember" not in names
        assert "recall" not in names
        assert "forget" not in names
        assert "list_memories" not in names

    def test_memory_add_writes_to_file(self, service, file_memory):
        svc, _ = service
        tools = {t.name: t for t in svc._build_tools("claude", "m", 0.7, 1024)}
        out = tools["memory_add"].invoke({"target": "user", "text": "测试条目"})
        result = json.loads(out)
        assert result["saved"] is True
        assert "测试条目" in file_memory.load(USER)

    def test_memory_add_reports_limit_error(self, service):
        svc, _ = service
        tools = {t.name: t for t in svc._build_tools("claude", "m", 0.7, 1024)}
        out = tools["memory_add"].invoke({"target": "user", "text": "x" * 9999})
        result = json.loads(out)
        assert result["saved"] is False
        assert "limit" in result["reason"].lower()

    def test_memory_replace_substitutes(self, service, file_memory):
        svc, _ = service
        file_memory.add(USER, "原始偏好")
        tools = {t.name: t for t in svc._build_tools("claude", "m", 0.7, 1024)}
        out = tools["memory_replace"].invoke({"target": "user", "old_text": "原始偏好", "new_text": "新偏好"})
        assert json.loads(out)["replaced"] is True
        assert "新偏好" in file_memory.load(USER)

    def test_memory_remove_deletes(self, service, file_memory):
        svc, _ = service
        file_memory.add(USER, "要删的条目")
        tools = {t.name: t for t in svc._build_tools("claude", "m", 0.7, 1024)}
        out = tools["memory_remove"].invoke({"target": "user", "old_text": "要删的条目"})
        assert json.loads(out)["removed"] is True
        assert "要删的条目" not in file_memory.load(USER)

    def test_session_search_uses_store(self, service, store):
        store.upsert_agent_thread("t1", title="t", provider="claude", model="m")
        store.save_agent_message(thread_id="t1", role="user", content="小红书种草文案怎么写", provider="claude", model="m")
        svc, _ = service
        tools = {t.name: t for t in svc._build_tools("claude", "m", 0.7, 1024)}
        out = tools["session_search"].invoke({"query": "小红书", "limit": 5})
        result = json.loads(out)
        assert result["count"] == 1
        assert "种草" in result["messages"][0]["content"]
