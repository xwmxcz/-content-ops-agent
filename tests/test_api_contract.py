from datetime import datetime, timedelta
import json
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest
from sqlalchemy import text

from src.api.dependencies import get_chat_agent_service, get_litellm_client, get_publish_service, get_store
from src.api.main import app
from src.api.schemas.content import GenerateRequest
from src.api.services.chat_agent import ChatAgentService
from src.api.services.publish_service import PublishService
from src.api.schemas.models import ModelInfo
from src.api.routes import media as media_routes
from src.api.routes import models as model_routes
from src.llm.litellm_client import LLMGenerationError
from src.models import ContentType, GeneratedContent


class FakeLLMClient:
    def __init__(self):
        self.calls = []
        self.fail_on_call = None

    async def generate_from_prompts(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_on_call == len(self.calls):
            raise LLMGenerationError("LLM request failed")

        system_prompt = kwargs.get("system_prompt", "")
        if "senior content strategist" in system_prompt:
            return "Audience: creators\nAngle: practical AI workflow\nStructure: hook, steps, CTA"
        if "platform-native content writer" in system_prompt:
            return "Draft post\nUse AI to plan, write, and review content faster."
        if "professional content editor" in system_prompt:
            return "Final post\nUse AI to build a repeatable content workflow without losing your voice."
        if "content quality reviewer" in system_prompt:
            return "Score: 91\nStrengths: clear and useful\nRisks: add one concrete example"
        return "【标题】\n测试标题\n\n【正文】\n测试正文\n\n【标签】\nAI 效率"

    async def generate(self, **kwargs):
        return "Agent reply"


class FakeChatFactory:
    def __init__(self):
        self.calls = []
        self.tool_mode = False
        self.tool_call_spec = None  # {"name": str, "args": dict}
        self.flaky_mode = False
        self.flaky_target = "view_content"
        self.flaky_max_attempts = 3
        self.plan_response = None  # str returned when temperature == PLANNER_TEMPERATURE (0.3)
        self.intent_response = None  # str returned when temperature == INTENT_TEMPERATURE (0.1)

    def __call__(self, provider, model, temperature, max_tokens):
        return FakeChatModel(self, provider, model, temperature, max_tokens)


class FakeChatModel:
    def __init__(self, factory, provider, model, temperature, max_tokens):
        self.factory = factory
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.factory.calls.append(
            {
                "provider": self.provider,
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "messages": messages,
                "tools": self.tools,
            }
        )
        if self.factory.intent_response is not None and self.temperature == 0.1:
            return AIMessage(content=self.factory.intent_response)
        if self.temperature == 0.1:
            last_human = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
            text = str(last_human).lower()
            if "recent" in text or "之前写过" in str(last_human) or "content 99999" in text:
                return AIMessage(content='{"name":"content_search","confidence":0.92,"slots":{},"clarification":null}')
            if "calendar week" in text or "schedule" in text:
                return AIMessage(content='{"name":"schedule_propose","confidence":0.92,"slots":{},"clarification":null}')
            if "practical" in text:
                return AIMessage(content='{"name":"content_refine","confidence":0.9,"slots":{},"clarification":null}')
            return AIMessage(content='{"name":"unknown","confidence":0.8,"slots":{},"clarification":null}')
        if self.factory.plan_response is not None and self.temperature == 0.3:
            return AIMessage(content=self.factory.plan_response)
        if self.factory.flaky_mode:
            tool_message_count = sum(1 for m in messages if isinstance(m, ToolMessage))
            if tool_message_count < self.factory.flaky_max_attempts:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": self.factory.flaky_target,
                            "args": {"content_id": 99999},
                            "id": f"call_{tool_message_count + 1}",
                        }
                    ],
                )
            return AIMessage(content="Recovered.")
        if self.factory.tool_mode and not any(isinstance(message, ToolMessage) for message in messages):
            spec = self.factory.tool_call_spec or {"name": "list_recent_contents", "args": {"limit": 5}}
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": spec["name"],
                        "args": spec["args"],
                        "id": "call_1",
                    }
                ],
            )
        return AIMessage(content="Agent reply")


class FakeXiaohongshuMcpClient:
    def __init__(self):
        self.calls = []

    async def check_login_status(self):
        return {"text": "Logged in", "data": {"logged_in": True}}

    async def publish_content(self, arguments):
        self.calls.append(("publish_content", arguments))
        return {"text": "Image post published", "data": {"post_id": "xhs-image-1"}}

    async def publish_with_video(self, arguments):
        self.calls.append(("publish_with_video", arguments))
        return {"text": "Video post published", "data": {"post_id": "xhs-video-1"}}


@pytest.fixture
def fake_llm():
    return FakeLLMClient()


@pytest.fixture
def fake_chat_factory():
    return FakeChatFactory()


@pytest.fixture
def fake_xhs_mcp():
    return FakeXiaohongshuMcpClient()


@pytest.fixture
def client(store, fake_llm, fake_chat_factory, fake_xhs_mcp, monkeypatch):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_litellm_client] = lambda: fake_llm
    app.dependency_overrides[get_chat_agent_service] = lambda: ChatAgentService(
        store=store,
        llm=fake_llm,
        model_factory=fake_chat_factory,
    )
    app.dependency_overrides[get_publish_service] = lambda: PublishService(store=store, mcp_client=fake_xhs_mcp)
    monkeypatch.setattr(
        "src.jobs.runner.create_publish_service",
        lambda current_store: PublishService(store=current_store, mcp_client=fake_xhs_mcp),
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_chat_persists_thread_messages_and_model(client, store, fake_chat_factory):
    response = client.post(
        "/api/agent/chat",
        json={
            "message": "Plan a content week",
            "thread_id": "thread-a",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "temperature": 0.4,
            "max_tokens": 1024,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_id"] == "thread-a"
    assert payload["provider"] == "siliconflow"
    assert payload["model"] == "Qwen/Qwen2.5-7B-Instruct"
    assert payload["response"] == "Agent reply"

    messages = store.list_agent_messages("thread-a")
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["model"] == "Qwen/Qwen2.5-7B-Instruct"
    assert any(c["provider"] == "siliconflow" for c in fake_chat_factory.calls)
    assert any(c["temperature"] == 0.4 for c in fake_chat_factory.calls)

    second_response = client.post(
        "/api/agent/chat",
        json={
            "message": "Now make it more practical",
            "thread_id": "thread-a",
            "provider": "deepseek",
            "model": "deepseek-chat",
        },
    )

    assert second_response.status_code == 200
    assert second_response.json()["provider"] == "deepseek"
    second_call_messages = next(
        c["messages"] for c in reversed(fake_chat_factory.calls) if c["provider"] == "deepseek" and c["temperature"] == 0.7
    )
    assert any(isinstance(message, HumanMessage) and message.content == "Plan a content week" for message in second_call_messages)
    assert any(isinstance(message, AIMessage) and message.content == "Agent reply" for message in second_call_messages)
    assert store.list_agent_messages("thread-a")[-1]["model"] == "deepseek-chat"


def test_agent_chat_returns_and_saves_tool_events(client, store, fake_chat_factory):
    fake_chat_factory.tool_mode = True

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "Show recent content",
            "thread_id": "thread-tools",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_events"][0]["name"] == "list_recent_contents"
    assert payload["tool_events"][0]["status"] == "completed"

    messages = store.list_agent_messages("thread-tools")
    assert messages[-1]["tool_events"][0]["name"] == "list_recent_contents"


def test_search_history_tool_returns_persisted_content(client, store, fake_chat_factory):
    store.save_content(
        GeneratedContent(
            title="周末徒步路线推荐",
            content="本期我们盘点 5 条适合周末出行的徒步路线。",
            tags=["徒步", "户外"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
        keywords=["徒步", "周末"],
    )
    store.save_content(
        GeneratedContent(
            title="咖啡馆探店指南",
            content="一个不爱户外只爱咖啡的人。",
            tags=["咖啡"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
        keywords=["咖啡"],
    )

    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "search_history", "args": {"query": "徒步", "limit": 5}}

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "之前写过哪些徒步主题的内容？",
            "thread_id": "thread-search",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_events"][0]["name"] == "search_history"
    assert payload["tool_events"][0]["status"] == "completed"

    import json as _json
    matches = _json.loads(payload["tool_events"][0]["output"])
    assert any("徒步" in (item.get("title") or "") for item in matches)
    assert all("咖啡馆探店指南" not in (item.get("title") or "") for item in matches)


def test_chat_agent_retries_failed_tool(client, store, fake_chat_factory, monkeypatch):
    """Agent should reflect tool failure into a retry: 1 failed + 1 completed event for the same tool."""
    call_state = {"n": 0}

    def flaky_view_content(content_id):
        """Read a saved content item by id (flaky variant for retry tests)."""
        call_state["n"] += 1
        if call_state["n"] < 3:
            raise LookupError(f"Content {content_id} was not found (attempt {call_state['n']})")
        return _json_module.dumps({"id": content_id, "title": "Recovered", "content": "ok"}, ensure_ascii=False)

    import json as _json_module
    from src.api.services import chat_agent as chat_agent_mod

    real_build_tools = chat_agent_mod.ChatAgentService._build_tools

    def build_tools_with_flaky(self, provider, model, temperature, max_tokens, allowed_tools=None):
        tools = real_build_tools(self, provider, model, temperature, max_tokens, allowed_tools=allowed_tools)
        from langchain_core.tools import StructuredTool
        replaced = [t for t in tools if t.name != "view_content"]
        replaced.append(StructuredTool.from_function(func=flaky_view_content, name="view_content"))
        if allowed_tools is None:
            return replaced
        allowed = set(allowed_tools)
        return [tool for tool in replaced if tool.name in allowed]
        return replaced

    monkeypatch.setattr(chat_agent_mod.ChatAgentService, "_build_tools", build_tools_with_flaky)

    fake_chat_factory.flaky_mode = True
    fake_chat_factory.flaky_target = "view_content"
    fake_chat_factory.flaky_max_attempts = 3

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "Show content 99999",
            "thread_id": "thread-retry",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    events = payload["tool_events"]
    assert len(events) >= 3, f"expected at least 3 events, got {len(events)}: {events}"
    assert events[0]["name"] == "view_content"
    assert events[0]["status"] == "failed"
    assert events[0]["attempt"] == 1
    assert events[1]["status"] == "failed"
    assert events[1]["attempt"] == 2
    assert events[2]["status"] == "completed"
    assert events[2]["attempt"] == 3
    assert payload["response"] == "Recovered."


def test_chat_returns_plan_when_planner_succeeds(client, fake_chat_factory):
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "list_recent_contents", "args": {"limit": 3}}
    fake_chat_factory.plan_response = (
        '[{"index": 1, "description": "Look up recent posts", "tool_hint": "list_recent_contents"},'
        ' {"index": 2, "description": "Summarize them", "tool_hint": null}]'
    )

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "Summarize my recent posts",
            "thread_id": "thread-plan-ok",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["plan"]) == 2
    assert payload["plan"][0]["description"] == "Look up recent posts"
    assert payload["plan"][0]["tool_hint"] == "list_recent_contents"
    assert payload["plan"][0]["status"] == "completed"
    assert payload["plan"][1]["status"] == "skipped"
    assert payload["tool_events"][0]["plan_step_index"] == 1


def test_chat_falls_back_when_plan_json_invalid(client, fake_chat_factory):
    fake_chat_factory.plan_response = "I'll just wing it"

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "Just chat with me",
            "thread_id": "thread-plan-bad",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"] == []
    assert payload["response"] == "Agent reply"


def test_chat_persists_plan_across_thread_reload(client, fake_chat_factory):
    fake_chat_factory.tool_mode = True
    fake_chat_factory.plan_response = (
        '[{"index": 1, "description": "Find recent items", "tool_hint": "list_recent_contents"}]'
    )

    chat_response = client.post(
        "/api/agent/chat",
        json={
            "message": "Show recent items",
            "thread_id": "thread-plan-persist",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    assert chat_response.status_code == 200
    expected_plan = chat_response.json()["plan"]
    assert expected_plan, "plan should be populated"

    messages_response = client.get("/api/agent/threads/thread-plan-persist/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert assistant["plan"] == expected_plan


def test_chat_returns_and_persists_intent(client):
    response = client.post(
        "/api/agent/chat",
        json={
            "message": "Show recent items",
            "thread_id": "thread-intent",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["name"] == "content_search"

    messages_response = client.get("/api/agent/threads/thread-intent/messages")
    assert messages_response.status_code == 200
    assistant = next(m for m in messages_response.json() if m["role"] == "assistant")
    assert assistant["intent"]["name"] == "content_search"


def test_schedule_propose_intent_blocks_commit_tool(client, fake_chat_factory):
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {
        "name": "commit_publishing_schedule",
        "args": {"plan": [{"content_id": 1, "platform": "xiaohongshu", "scheduled_date": "2026-06-20"}]},
    }

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "帮我排下周发布计划",
            "thread_id": "thread-schedule-propose",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["name"] == "schedule_propose"
    assert "commit_publishing_schedule" not in payload["intent"]["allowed_tools"]
    assert payload["tool_events"][0]["status"] == "failed"
    assert "Unknown tool: commit_publishing_schedule" in payload["tool_events"][0]["output"]


def test_schedule_commit_intent_reuses_prior_proposal(client, store):
    store.upsert_agent_thread("thread-schedule-commit", title="schedule", provider="siliconflow", model="Qwen/Qwen2.5-7B-Instruct")
    store.save_agent_message(
        thread_id="thread-schedule-commit",
        role="assistant",
        content="这是上一步生成的发布计划，请确认。",
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
        intent={
            "name": "schedule_propose",
            "confidence": 0.95,
            "slots": {},
            "requires_confirmation": False,
            "allowed_tools": ["list_recent_contents", "search_history", "view_calendar", "propose_publishing_schedule"],
            "route_surface": "chat",
            "route_reason": None,
            "clarification": None,
        },
        tool_events=[
            {
                "name": "propose_publishing_schedule",
                "args": {},
                "output": '{"plan":[{"content_id":1,"platform":"xiaohongshu","scheduled_date":"2026-06-20"}],"committed":false}',
                "status": "completed",
                "attempt": 1,
                "duration_ms": 10,
            }
        ],
    )

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "好的，开始排吧",
            "thread_id": "thread-schedule-commit",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["name"] == "schedule_commit"
    assert payload["intent"]["allowed_tools"] == ["commit_publishing_schedule"]
    assert payload["intent"]["slots"]["proposal_plan"][0]["content_id"] == 1


@pytest.mark.parametrize(
    ("forged_intent", "tool_name", "tool_args"),
    [
        (
            "action_confirm",
            "add_to_calendar",
            {"content_id": 1, "publish_date": "2099-01-02", "platform": "xiaohongshu"},
        ),
        (
            "schedule_commit",
            "commit_publishing_schedule",
            {
                "plan": [
                    {
                        "content_id": 1,
                        "platform": "xiaohongshu",
                        "scheduled_date": "2099-01-02",
                    }
                ]
            },
        ),
    ],
)
def test_llm_forged_confirmation_on_explicit_rejection_cannot_write_calendar(
    client,
    store,
    fake_chat_factory,
    forged_intent,
    tool_name,
    tool_args,
):
    content_id = store.save_content(
        GeneratedContent(
            title="Do not schedule",
            content="The user has not approved this.",
            tags=["security"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    assert content_id == 1
    thread_id = f"thread-forged-{forged_intent}"
    store.upsert_agent_thread(
        thread_id,
        title="proposal",
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )
    proposal_event = {
        "name": "add_to_calendar",
        "args": tool_args,
        "output": "proposal",
        "status": "proposed",
        "attempt": 1,
        "duration_ms": 1,
    }
    prior_intent = {"name": "calendar_view"}
    if forged_intent == "schedule_commit":
        proposal_event = {
            "name": "propose_publishing_schedule",
            "args": {},
            "output": json.dumps({"plan": tool_args["plan"], "committed": False}),
            "status": "completed",
            "attempt": 1,
            "duration_ms": 1,
        }
        prior_intent = {"name": "schedule_propose"}
    store.save_agent_message(
        thread_id=thread_id,
        role="assistant",
        content="Please confirm this proposal.",
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
        intent=prior_intent,
        tool_events=[proposal_event],
    )

    fake_chat_factory.intent_response = json.dumps(
        {"name": forged_intent, "confidence": 0.99, "slots": {}}
    )
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": tool_name, "args": tool_args}

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "I explicitly reject the earlier operation and want only an explanation instead",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["name"] == "unknown"
    assert payload["intent"]["allowed_tools"] == []
    assert payload["tool_events"][0]["status"] == "failed"
    assert f"Unknown tool: {tool_name}" in payload["tool_events"][0]["output"]
    assert store.get_calendar_events(
        datetime(2099, 1, 1).date(), datetime(2099, 1, 3).date()
    ) == []


def test_proposed_action_routes_cover_propose_confirm_cancel(client, store):
    store.upsert_agent_thread(
        "thread-action-routes",
        title="actions",
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )
    args = {"target": "user", "text": "route proposal"}

    created = client.post(
        "/api/agent/actions",
        json={
            "thread_id": "thread-action-routes",
            "tool_name": "memory_add",
            "args": args,
        },
    )
    assert created.status_code == 201
    action = created.json()
    assert action["status"] == "proposed"
    assert action["args_hash"]

    listed = client.get("/api/agent/threads/thread-action-routes/actions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [action["id"]]

    confirmed = client.post(f"/api/agent/actions/{action['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    # A second confirmation must not mint another capability.
    assert client.post(f"/api/agent/actions/{action['id']}/confirm").status_code == 409

    cancelled = client.post(f"/api/agent/actions/{action['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/agent/actions/{action['id']}/cancel").status_code == 409


def test_propose_action_rejects_read_only_tool_and_unknown_thread(client, store):
    store.upsert_agent_thread(
        "thread-action-validate",
        title="actions",
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )

    read_only = client.post(
        "/api/agent/actions",
        json={
            "thread_id": "thread-action-validate",
            "tool_name": "view_content",
            "args": {"content_id": 1},
        },
    )
    assert read_only.status_code == 400

    missing_thread = client.post(
        "/api/agent/actions",
        json={
            "thread_id": "thread-does-not-exist",
            "tool_name": "memory_add",
            "args": {"target": "user", "text": "x"},
        },
    )
    assert missing_thread.status_code == 404


def test_confirm_and_cancel_unknown_action_return_404(client):
    assert client.post("/api/agent/actions/act_missing/confirm").status_code == 404
    assert client.post("/api/agent/actions/act_missing/cancel").status_code == 404


def test_chat_write_requires_confirmation_then_writes_content_once(
    client, store, fake_chat_factory
):
    """Full propose -> confirm -> execute cycle produces exactly one DB row."""
    tool_args = {"topic": "capability cycle topic", "content_type": "xiaohongshu"}
    thread_id = "thread-capability-cycle"
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "create_content", "args": tool_args}

    first = client.post(
        "/api/agent/chat",
        json={
            "message": "\u5199\u4e00\u7bc7\u5c0f\u7ea2\u4e66\u7b14\u8bb0",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    assert first.status_code == 200
    proposed_event = first.json()["tool_events"][0]
    assert proposed_event["status"] == "proposed"
    action_id = proposed_event["action_id"]
    assert action_id
    # Nothing is written until the user confirms.
    assert store.list_contents(limit=10) == []

    confirm = client.post(
        "/api/agent/chat",
        json={
            "message": "\u597d\u7684",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["intent"]["name"] == "action_confirm"
    assert confirm.json()["tool_events"][0]["status"] == "completed"
    assert len(store.list_contents(limit=10)) == 1
    assert store.get_proposed_action(action_id)["status"] == "consumed"

    # Replaying the same confirmation must not create a second content row.
    replay = client.post(
        "/api/agent/chat",
        json={
            "message": "\u597d\u7684",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    assert replay.status_code == 200
    assert len(store.list_contents(limit=10)) == 1


def test_chat_write_records_the_consumed_capability_as_its_idempotency_key(
    client, store, fake_chat_factory
):
    """The chat lane's request identity is the consumed ``proposed_actions.id``.

    Without that binding the write would run unguarded, so a keyed replay could
    not return the original result. Asserting the ledger row carries the action id
    is what proves the key reached the service layer.
    """
    tool_args = {"topic": "ledger binding topic", "content_type": "xiaohongshu"}
    thread_id = "thread-ledger-binding"
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "create_content", "args": tool_args}

    proposal = client.post(
        "/api/agent/chat",
        json={
            "message": "\u5199\u4e00\u7bc7\u5c0f\u7ea2\u4e66\u7b14\u8bb0",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    action_id = proposal.json()["tool_events"][0]["action_id"]

    confirm = client.post(
        "/api/agent/chat",
        json={
            "message": "\u597d\u7684",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    assert confirm.status_code == 200
    assert len(store.list_contents(limit=10)) == 1

    record = store.get_idempotency_record(scope="content.create", key=action_id)
    assert record is not None
    assert record["status"] == "completed"
    assert record["result"]["content_id"] == store.list_contents(limit=10)[0]["id"]


def test_read_only_chat_tool_writes_no_ledger_row(client, store, fake_chat_factory):
    """Read tools consume no capability, so they must stay unkeyed."""
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "view_calendar", "args": {"days": 7}}

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "\u770b\u4e0b\u65e5\u5386",
            "thread_id": "thread-readonly-ledger",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    with store.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM idempotency_records")).scalar_one() == 0


def test_calendar_route_idempotency_key_returns_one_event(client, store):
    content_id = store.save_content(
        GeneratedContent(
            content="calendar body",
            title="calendar",
            tags=[],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    payload = {
        "content_id": content_id,
        "platform": "xiaohongshu",
        "scheduled_date": (datetime.now().date() + timedelta(days=3)).isoformat(),
    }
    headers = {"Idempotency-Key": "cal-route-1"}

    first = client.post("/api/calendar/events", json=payload, headers=headers)
    second = client.post("/api/calendar/events", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["event_id"] == second.json()["event_id"]
    with store.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM calendar_events")).scalar_one() == 1


def test_calendar_route_without_a_key_keeps_creating_events(client, store):
    """Same-slot rescheduling is legitimate, so an unkeyed repeat must still write."""
    content_id = store.save_content(
        GeneratedContent(
            content="calendar body",
            title="calendar",
            tags=[],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    payload = {
        "content_id": content_id,
        "platform": "xiaohongshu",
        "scheduled_date": (datetime.now().date() + timedelta(days=4)).isoformat(),
    }

    client.post("/api/calendar/events", json=payload)
    client.post("/api/calendar/events", json=payload)

    with store.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM calendar_events")).scalar_one() == 2


def test_calendar_route_rejects_a_key_reused_with_different_arguments(client, store):
    content_id = store.save_content(
        GeneratedContent(
            content="calendar body",
            title="calendar",
            tags=[],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    headers = {"Idempotency-Key": "cal-route-conflict"}
    base_date = datetime.now().date() + timedelta(days=5)

    first = client.post(
        "/api/calendar/events",
        json={
            "content_id": content_id,
            "platform": "xiaohongshu",
            "scheduled_date": base_date.isoformat(),
        },
        headers=headers,
    )
    assert first.status_code == 201

    conflict = client.post(
        "/api/calendar/events",
        json={
            "content_id": content_id,
            "platform": "weibo",
            "scheduled_date": base_date.isoformat(),
        },
        headers=headers,
    )

    # Returning the first result here would silently discard the second request.
    assert conflict.status_code == 422
    with store.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM calendar_events")).scalar_one() == 1


def test_expired_capability_denies_chat_confirmation_write(client, store, fake_chat_factory):
    tool_args = {"topic": "expiring topic", "content_type": "xiaohongshu"}
    thread_id = "thread-capability-expired"
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "create_content", "args": tool_args}
    client.post(
        "/api/agent/chat",
        json={
            "message": "\u5199\u4e00\u7bc7\u5c0f\u7ea2\u4e66\u7b14\u8bb0",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )
    assert store.list_contents(limit=10) == []
    with store.engine.begin() as connection:
        connection.execute(
            text("UPDATE proposed_actions SET expires_at = :past WHERE thread_id = :thread"),
            {"past": datetime.now() - timedelta(seconds=5), "thread": thread_id},
        )

    confirm = client.post(
        "/api/agent/chat",
        json={
            "message": "\u597d\u7684",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert confirm.status_code == 200
    # The stale approval is not executable and no content row exists.
    assert store.list_contents(limit=10) == []


def test_legacy_transcript_proposal_denies_chat_write_end_to_end(
    client, store, fake_chat_factory
):
    """A Phase 0 thread has a `proposed` tool event but no durable capability.

    Confirming it must fail closed through the whole stack. The policy-layer
    tests hand-bind ``action_id=None``; this drives a real chat turn so that
    handing the transcript fallback an action id, or letting it outrank the
    durable lookup, is caught here.
    """
    thread_id = "thread-legacy-no-capability"
    tool_args = {"topic": "legacy proposal topic", "content_type": "xiaohongshu"}
    store.upsert_agent_thread(
        thread_id,
        title="legacy",
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )
    store.save_agent_message(
        thread_id=thread_id,
        role="assistant",
        content="Please confirm this proposal.",
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
        intent={"name": "content_create"},
        tool_events=[
            {
                "name": "create_content",
                "args": tool_args,
                "output": "proposal",
                "status": "proposed",
                "attempt": 1,
                "duration_ms": 1,
            }
        ],
    )
    # The Phase 0 transcript shape carries no durable row.
    with store.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM proposed_actions")).scalar_one() == 0

    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "create_content", "args": tool_args}

    confirm = client.post(
        "/api/agent/chat",
        json={
            "message": "\u597d\u7684",
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert confirm.status_code == 200
    event = confirm.json()["tool_events"][0]
    assert event["status"] == "failed"
    assert "no durable confirmed capability" in event["output"]
    # The real side effect count is what matters: no content, and no capability
    # was minted to make the legacy proposal retroactively executable.
    assert store.list_contents(limit=10) == []
    with store.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM proposed_actions")).scalar_one() == 0


def test_research_heavy_create_returns_studio_suggestion(client, fake_chat_factory):
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "create_content", "args": {"topic": "x", "content_type": "xiaohongshu"}}

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "写一篇 2026 最新模型横评，带事实核查",
            "thread_id": "thread-studio-intent",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["name"] == "content_create"
    assert payload["intent"]["route_surface"] == "studio"
    assert payload["tool_events"] == []
    assert payload["plan"] == []


def test_ambiguous_request_returns_clarify_without_tools(client, fake_chat_factory):
    fake_chat_factory.tool_mode = True
    fake_chat_factory.tool_call_spec = {"name": "refine_content", "args": {"content_id": 1, "instruction": "polish it"}}

    response = client.post(
        "/api/agent/chat",
        json={
            "message": "帮我处理一下这篇",
            "thread_id": "thread-clarify-intent",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"]["name"] == "clarify"
    assert payload["tool_events"] == []
    assert payload["plan"] == []


def test_agent_thread_endpoints(client):
    client.post(
        "/api/agent/chat",
        json={
            "message": "Create a thread",
            "thread_id": "thread-api",
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    threads_response = client.get("/api/agent/threads")
    assert threads_response.status_code == 200
    assert any(thread["id"] == "thread-api" for thread in threads_response.json())

    messages_response = client.get("/api/agent/threads/thread-api/messages")
    assert messages_response.status_code == 200
    assert [message["role"] for message in messages_response.json()] == ["user", "assistant"]

    delete_response = client.delete("/api/agent/threads/thread-api")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    missing_response = client.get("/api/agent/threads/thread-api/messages")
    assert missing_response.status_code == 404


def _send_chat(client, *, thread_id: str, message: str = "hello"):
    return client.post(
        "/api/agent/chat",
        json={
            "message": message,
            "thread_id": thread_id,
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )


def test_patch_thread_rename_locks_title(client, store):
    _send_chat(client, thread_id="thread-rename", message="initial topic")

    # Auto-derived title from the first user message.
    threads_before = client.get("/api/agent/threads").json()
    auto_title = next(t["title"] for t in threads_before if t["id"] == "thread-rename")
    assert auto_title  # auto-generated

    rename = client.patch("/api/agent/threads/thread-rename", json={"title": "My pinned title"})
    assert rename.status_code == 200
    body = rename.json()
    assert body["title"] == "My pinned title"
    assert body["title_pinned"] is True

    # A follow-up message must NOT clobber the manual title.
    _send_chat(client, thread_id="thread-rename", message="follow up message that would otherwise become the title")
    threads_after = client.get("/api/agent/threads").json()
    after = next(t for t in threads_after if t["id"] == "thread-rename")
    assert after["title"] == "My pinned title"
    assert after["title_pinned"] is True


def test_patch_thread_pin_orders_list(client):
    _send_chat(client, thread_id="thread-old", message="old one")
    _send_chat(client, thread_id="thread-new", message="newer one")

    # Without pinning, "thread-new" sits first (most recently updated).
    default = client.get("/api/agent/threads").json()
    assert default[0]["id"] == "thread-new"

    pin = client.patch("/api/agent/threads/thread-old", json={"pinned": True})
    assert pin.status_code == 200
    assert pin.json()["pinned"] is True

    pinned_first = client.get("/api/agent/threads").json()
    assert pinned_first[0]["id"] == "thread-old"
    assert pinned_first[0]["pinned"] is True


def test_patch_thread_archive_filters_list(client):
    _send_chat(client, thread_id="thread-archive")

    archive = client.patch("/api/agent/threads/thread-archive", json={"archived": True})
    assert archive.status_code == 200
    assert archive.json()["archived"] is True

    default = client.get("/api/agent/threads").json()
    assert all(t["id"] != "thread-archive" for t in default)

    with_archived = client.get("/api/agent/threads", params={"include_archived": True}).json()
    assert any(t["id"] == "thread-archive" and t["archived"] for t in with_archived)


def test_list_threads_pagination(client):
    for i in range(3):
        _send_chat(client, thread_id=f"thread-page-{i}", message=f"page {i}")

    page_one = client.get("/api/agent/threads", params={"limit": 2, "offset": 0}).json()
    page_two = client.get("/api/agent/threads", params={"limit": 2, "offset": 2}).json()
    assert len(page_one) == 2
    assert len(page_two) == 1
    page_one_ids = {t["id"] for t in page_one}
    page_two_ids = {t["id"] for t in page_two}
    assert page_one_ids.isdisjoint(page_two_ids)


def test_list_messages_before_id(client):
    for i in range(5):
        _send_chat(client, thread_id="thread-cursor", message=f"msg {i}")

    all_messages = client.get("/api/agent/threads/thread-cursor/messages").json()
    assert len(all_messages) == 10  # 5 user + 5 assistant

    cursor_id = all_messages[5]["id"]  # split point
    older = client.get(
        "/api/agent/threads/thread-cursor/messages",
        params={"limit": 100, "before_id": cursor_id},
    ).json()
    assert all(m["id"] < cursor_id for m in older)
    assert len(older) == 5


def test_search_threads(client):
    _send_chat(client, thread_id="thread-search", message="please plan a calendar week for me")
    _send_chat(client, thread_id="thread-other", message="completely unrelated note")

    response = client.get("/api/agent/threads/search", params={"q": "calendar"})
    assert response.status_code == 200
    hits = response.json()
    assert any(h["thread_id"] == "thread-search" for h in hits)
    for hit in hits:
        assert "message_id" in hit and "thread_id" in hit and "content" in hit


def test_patch_thread_rejects_empty_payload(client):
    _send_chat(client, thread_id="thread-empty-patch")
    response = client.patch("/api/agent/threads/thread-empty-patch", json={})
    assert response.status_code == 422


def test_patch_missing_thread_returns_404(client):
    response = client.patch("/api/agent/threads/does-not-exist", json={"title": "x"})
    assert response.status_code == 404


def test_models_contract(client, monkeypatch):
    async def no_dynamic_models(provider: str):
        return None

    monkeypatch.setattr(model_routes, "fetch_provider_models", no_dynamic_models)

    response = client.get("/api/models")
    assert response.status_code == 200
    providers = response.json()
    assert {provider["id"] for provider in providers} >= {"claude", "siliconflow", "deepseek", "moonshot"}


def test_models_contract_includes_dynamic_provider_models(client, monkeypatch):
    dynamic_models = {
        "claude": [ModelInfo(id="claude-sonnet-4-20250514", name="Claude Sonnet 4")],
        "siliconflow": [
            ModelInfo(id="Qwen/Qwen2.5-7B-Instruct", name="Qwen2.5 7B Instruct"),
            ModelInfo(id="deepseek-ai/DeepSeek-R1", name="deepseek-ai/DeepSeek-R1"),
        ],
        "deepseek": [ModelInfo(id="deepseek-reasoner", name="DeepSeek Reasoner")],
        "moonshot": [ModelInfo(id="kimi-k2.6", name="Kimi K2.6")],
    }

    async def fake_dynamic_models(provider: str):
        return dynamic_models.get(provider)

    monkeypatch.setattr(model_routes, "fetch_provider_models", fake_dynamic_models)

    response = client.get("/api/models")

    assert response.status_code == 200
    providers = {provider["id"]: provider for provider in response.json()}
    assert providers["claude"]["models"][0]["id"] == "claude-sonnet-4-20250514"
    assert {model["id"] for model in providers["siliconflow"]["models"]} >= {"deepseek-ai/DeepSeek-R1"}
    assert providers["deepseek"]["models"][0]["id"] == "deepseek-reasoner"
    assert providers["moonshot"]["models"][0]["id"] == "kimi-k2.6"


def test_generate_request_schema_accepts_core_fields():
    request = GenerateRequest(topic="测试主题", content_type=ContentType.XIAOHONGSHU)
    assert request.style.value == "casual"
    assert request.length == "medium"


def test_generate_rejects_invalid_provider(client):
    response = client.post(
        "/api/content/generate",
        json={
            "topic": "测试主题",
            "content_type": "xiaohongshu",
            "provider": "unknown",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown provider: unknown"


def test_generate_rejects_invalid_length(client):
    response = client.post(
        "/api/content/generate",
        json={
            "topic": "测试主题",
            "content_type": "xiaohongshu",
            "length": "extra-long",
        },
    )

    assert response.status_code == 422


def test_generate_maps_llm_failures_to_bad_gateway(client, fake_llm):
    fake_llm.fail_on_call = 1

    response = client.post(
        "/api/content/generate",
        json={
            "topic": "测试主题",
            "content_type": "xiaohongshu",
            "provider": "siliconflow",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM request failed"


def test_generate_persists_style_keywords_and_tags(client, store):
    response = client.post(
        "/api/content/generate",
        json={
            "topic": "测试主题",
            "content_type": "xiaohongshu",
            "style": "professional",
            "keywords": ["AI", "效率"],
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["style"] == "professional"
    assert payload["tags"] == ["AI", "效率"]

    stored = store.get_content(payload["id"])
    assert stored["style"] == "professional"
    assert stored["keywords"] == ["AI", "效率"]


def test_agent_run_returns_steps_and_saves_final_content(client, store, fake_llm):
    response = client.post(
        "/api/agent/run",
        json={
            "topic": "AI content workflow",
            "content_type": "xiaohongshu",
            "style": "professional",
            "keywords": ["AI", "workflow"],
            "provider": "siliconflow",
            "model": "Qwen/Qwen2.5-7B-Instruct",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert [step["id"] for step in payload["steps"]] == ["strategy", "writer", "editor", "review"]
    assert {step["status"] for step in payload["steps"]} == {"completed"}
    assert payload["final_content"]["content"].startswith("Final post")
    assert payload["saved_content_id"]
    assert payload["provider"] == "siliconflow"
    assert payload["model"] == "openai/Qwen/Qwen2.5-7B-Instruct"

    stored = store.get_content(payload["saved_content_id"])
    assert stored["status"] == "agent_final"
    assert stored["content"].startswith("Final post")
    assert stored["keywords"] == ["AI", "workflow"]
    assert fake_llm.calls[0]["provider"] == "siliconflow"
    assert fake_llm.calls[0]["model"] == "Qwen/Qwen2.5-7B-Instruct"


def test_agent_run_returns_failed_step_detail(client, fake_llm):
    fake_llm.fail_on_call = 3

    response = client.post(
        "/api/agent/run",
        json={
            "topic": "AI content workflow",
            "content_type": "xiaohongshu",
            "provider": "siliconflow",
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["message"] == "Editor Agent failed: LLM request failed"
    assert detail["steps"][-1]["id"] == "editor"
    assert detail["steps"][-1]["status"] == "failed"
    assert detail["steps"][-1]["error"] == "LLM request failed"


def test_publish_login_status_returns_connected(client):
    response = client.get("/api/publish/xiaohongshu/login-status")

    assert response.status_code == 200
    assert response.json()["connected"] is True


def test_media_upload_and_image_publish_flow(client, store, fake_xhs_mcp):
    content_id = store.save_content(
        GeneratedContent(
            title="测试图文",
            content="这是一条准备发布到小红书的图文内容。",
            tags=["AI", "效率"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )

    upload_response = client.post(
        "/api/media/upload",
        data={"content_id": str(content_id), "media_type": "image"},
        files={"file": ("cover.jpg", b"fake-image", "image/jpeg")},
    )

    assert upload_response.status_code == 201
    media_payload = upload_response.json()
    assert media_payload["media_type"] == "image"
    assert media_payload["file_url"] == f"/api/media/{media_payload['id']}/file"

    list_response = client.get(f"/api/content/{content_id}/media")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    publish_response = client.post(
        "/api/publish/xiaohongshu",
        json={"content_id": content_id, "publish_type": "image_post"},
    )

    assert publish_response.status_code == 202
    job_id = publish_response.json()["job_id"]
    job_response = client.get(f"/api/jobs/{job_id}")

    assert job_response.status_code == 200
    job_payload = job_response.json()
    assert job_payload["job_type"] == "publish_xiaohongshu"
    assert job_payload["status"] == "completed"
    assert job_payload["result"]["publication"]["status"] == "completed"
    assert store.get_content(content_id)["status"] == "published"
    assert fake_xhs_mcp.calls[0][0] == "publish_content"
    assert len(fake_xhs_mcp.calls[0][1]["images"]) == 1


def test_media_file_routes_do_not_touch_files_outside_media_root(client, store, tmp_path, monkeypatch):
    content_id = store.save_content(
        GeneratedContent(
            title="Unsafe media path",
            content="Keep route file access inside the configured media root.",
            tags=["media"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    media_root = tmp_path / "media"
    outside_file = tmp_path / "outside" / "keep.jpg"
    outside_file.parent.mkdir()
    outside_file.write_bytes(b"outside")
    monkeypatch.setattr(media_routes.config, "MEDIA_STORAGE_ROOT", str(media_root))

    asset = store.save_media_asset(
        content_id=content_id,
        media_type="image",
        source_type="upload",
        file_name="keep.jpg",
        file_path=str(outside_file),
        mime_type="image/jpeg",
    )

    file_response = client.get(f"/api/media/{asset['id']}/file")
    assert file_response.status_code == 404

    delete_response = client.delete(f"/api/media/{asset['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert outside_file.exists()
    assert store.get_media_asset(asset["id"]) is None


def test_publish_rejects_text_only_content(client, store):
    content_id = store.save_content(
        GeneratedContent(
            title="纯文字草稿",
            content="只有文字，没有媒体。",
            tags=["纯文字"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )

    response = client.post(
        "/api/publish/xiaohongshu",
        json={"content_id": content_id, "publish_type": "image_post"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Image posts require at least one uploaded image"


def test_schedule_publication_marks_content_scheduled_and_creates_calendar_event(client, store):
    content_id = store.save_content(
        GeneratedContent(
            title="定时内容",
            content="定时图文内容。",
            tags=["定时"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    client.post(
        "/api/media/upload",
        data={"content_id": str(content_id), "media_type": "image"},
        files={"file": ("cover.jpg", b"fake-image", "image/jpeg")},
    )

    scheduled_at = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat()
    response = client.post(
        "/api/publish/xiaohongshu/schedule",
        json={
            "content_id": content_id,
            "publish_type": "image_post",
            "scheduled_at": scheduled_at,
        },
    )

    assert response.status_code == 202
    job_response = client.get(f"/api/jobs/{response.json()['job_id']}")
    assert job_response.status_code == 200
    assert job_response.json()["result"]["publication"]["status"] == "scheduled"
    assert store.get_content(content_id)["status"] == "scheduled"

    events = store.get_calendar_events(datetime.now().date(), (datetime.now() + timedelta(days=2)).date())
    assert any(event["content_id"] == content_id and event["platform"] == "xiaohongshu" for event in events)


def test_archive_content_updates_status(client, store):
    content_id = store.save_content(
        GeneratedContent(
            title="Archive me",
            content="Archive this local record.",
            tags=["archive"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )

    response = client.post(f"/api/content/{content_id}/archive")

    assert response.status_code == 200
    assert response.json() == {"archived": True}
    assert store.get_content(content_id)["status"] == "archived"


def test_delete_content_cascades_local_records_and_files(client, store):
    content_id = store.save_content(
        GeneratedContent(
            title="Delete me",
            content="Delete this local record and all linked data.",
            tags=["cleanup"],
            content_type=ContentType.XIAOHONGSHU,
        ),
        style="casual",
    )
    upload_response = client.post(
        "/api/media/upload",
        data={"content_id": str(content_id), "media_type": "image"},
        files={"file": ("cover.jpg", b"fake-image", "image/jpeg")},
    )
    media_payload = upload_response.json()
    media_path = Path(media_payload["file_path"])

    store.create_publication(
        content_id=content_id,
        platform="xiaohongshu",
        publish_type="image_post",
        status="failed",
        title="Delete me",
        body="Delete this local record and all linked data.",
        request_payload={"images": [media_payload["file_path"]]},
    )
    store.save_calendar_event(content_id, "xiaohongshu", datetime.now().date())
    with store.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO content_metrics (content_id, platform, views, likes, comments, shares) "
                "VALUES (:content_id, :platform, 10, 2, 1, 0)"
            ),
            {"content_id": content_id, "platform": "xiaohongshu"},
        )

    response = client.delete(f"/api/content/{content_id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert store.get_content(content_id) is None
    assert store.list_media_assets(content_id) == []
    assert store.list_publications(content_id) == []
    assert store.get_calendar_events(datetime.now().date(), datetime.now().date()) == []
    with store.engine.begin() as connection:
        metrics_count = connection.execute(
            text("SELECT COUNT(*) FROM content_metrics WHERE content_id = :content_id"),
            {"content_id": content_id},
        ).scalar_one()
    assert metrics_count == 0
    assert not media_path.exists()
    assert not (Path("data/media") / str(content_id)).exists()
