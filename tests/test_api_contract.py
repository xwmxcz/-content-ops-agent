from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

from src.api.dependencies import get_chat_agent_service, get_litellm_client, get_store
from src.api.main import app
from src.api.schemas.content import GenerateRequest
from src.api.services.chat_agent import ChatAgentService
from src.api.schemas.models import ModelInfo
from src.api.routes import models as model_routes
from src.llm.litellm_client import LLMGenerationError
from src.models import ContentType
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
        if self.factory.tool_mode and not any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "list_recent_contents",
                        "args": {"limit": 5},
                        "id": "call_1",
                    }
                ],
            )
        return AIMessage(content="Agent reply")


@pytest.fixture
def fake_llm():
    return FakeLLMClient()


@pytest.fixture
def fake_chat_factory():
    return FakeChatFactory()


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
def client(store, fake_llm, fake_chat_factory):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_litellm_client] = lambda: fake_llm
    app.dependency_overrides[get_chat_agent_service] = lambda: ChatAgentService(
        store=store,
        llm=fake_llm,
        model_factory=fake_chat_factory,
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
    assert fake_chat_factory.calls[0]["provider"] == "siliconflow"
    assert fake_chat_factory.calls[0]["temperature"] == 0.4

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
    second_call_messages = fake_chat_factory.calls[-1]["messages"]
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
