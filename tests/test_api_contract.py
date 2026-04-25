from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from src.api.dependencies import get_litellm_client, get_store
from src.api.main import app
from src.api.schemas.content import GenerateRequest
from src.api.schemas.models import ModelInfo
from src.api.routes import models as model_routes
from src.models import ContentType
from src.storage import ContentStore


class FakeLLMClient:
    async def generate_from_prompts(self, **kwargs):
        return "【标题】\n测试标题\n\n【正文】\n测试正文\n\n【标签】\nAI 效率"


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
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_litellm_client] = lambda: FakeLLMClient()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
