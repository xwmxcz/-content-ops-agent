from datetime import datetime, timedelta
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
from src.storage import ContentStore


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
def store():
    db_path = Path("data/test_api_contract.db")
    if db_path.exists():
        db_path.unlink()
    content_store = ContentStore(db_path=str(db_path))
    yield content_store
    content_store.engine.dispose()
    if db_path.exists():
        db_path.unlink()


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
        c["messages"] for c in reversed(fake_chat_factory.calls) if c["provider"] == "deepseek" and c["temperature"] != 0.3
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

    def build_tools_with_flaky(self, provider, model, temperature, max_tokens):
        tools = real_build_tools(self, provider, model, temperature, max_tokens)
        from langchain_core.tools import StructuredTool
        replaced = [t for t in tools if t.name != "view_content"]
        replaced.append(StructuredTool.from_function(func=flaky_view_content, name="view_content"))
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
