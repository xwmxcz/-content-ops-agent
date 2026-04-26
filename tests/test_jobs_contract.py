from pathlib import Path

from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.storage import ContentStore


class FakeLLMClient:
    async def generate_from_prompts(self, **kwargs):
        system_prompt = kwargs.get("system_prompt", "")
        if "senior content strategist" in system_prompt:
            return "Audience: creators\nAngle: practical workflow"
        if "platform-native content writer" in system_prompt:
            return "Draft post\nUse AI to plan content."
        if "professional content editor" in system_prompt:
            return "Final post\nUse AI to build a repeatable content workflow."
        if "content quality reviewer" in system_prompt:
            return "Score: 91\nStrengths: clear\nRisks: none"
        return "【标题】\n测试标题\n\n【正文】\n测试正文\n\n【标签】\nAI 效率"


def test_content_generation_job_completes(monkeypatch):
    db_path = Path("data/test_jobs_contract.db")
    if db_path.exists():
        db_path.unlink()
    store = ContentStore(db_path=str(db_path))
    app.dependency_overrides[get_store] = lambda: store
    monkeypatch.setattr("src.jobs.runner.create_litellm_client", lambda: FakeLLMClient())

    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/jobs/content-generation",
                json={
                    "topic": "测试主题",
                    "content_type": "xiaohongshu",
                    "provider": "siliconflow",
                },
            )

            assert create_response.status_code == 202
            job_id = create_response.json()["id"]
            job_response = client.get(f"/api/jobs/{job_id}")

            assert job_response.status_code == 200
            payload = job_response.json()
            assert payload["status"] == "completed"
            assert payload["progress"] == 100
            assert payload["result"]["content"]["content"] == "测试正文"
    finally:
        app.dependency_overrides.clear()
        store.engine.dispose()
        if db_path.exists():
            db_path.unlink()


def test_agent_run_job_completes(monkeypatch):
    db_path = Path("data/test_jobs_agent_contract.db")
    if db_path.exists():
        db_path.unlink()
    store = ContentStore(db_path=str(db_path))
    app.dependency_overrides[get_store] = lambda: store
    monkeypatch.setattr("src.jobs.runner.create_litellm_client", lambda: FakeLLMClient())

    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/jobs/agent-run",
                json={
                    "topic": "AI workflow",
                    "content_type": "xiaohongshu",
                    "provider": "siliconflow",
                },
            )

            assert create_response.status_code == 202
            job_id = create_response.json()["id"]
            job_response = client.get(f"/api/jobs/{job_id}")

            assert job_response.status_code == 200
            payload = job_response.json()
            assert payload["status"] == "completed"
            assert payload["result"]["agent_run"]["final_content"]["content"].startswith("Final post")
    finally:
        app.dependency_overrides.clear()
        store.engine.dispose()
        if db_path.exists():
            db_path.unlink()


def test_job_capacity_limit_returns_429(monkeypatch):
    db_path = Path("data/test_jobs_capacity.db")
    if db_path.exists():
        db_path.unlink()
    store = ContentStore(db_path=str(db_path))
    app.dependency_overrides[get_store] = lambda: store
    monkeypatch.setattr("src.jobs.queue.config.MAX_PROVIDER_INFLIGHT_JOBS", 0)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/jobs/content-generation",
                json={
                    "topic": "测试主题",
                    "content_type": "xiaohongshu",
                    "provider": "siliconflow",
                },
            )

            assert response.status_code == 429
            assert response.headers["retry-after"] == "10"
    finally:
        app.dependency_overrides.clear()
        store.engine.dispose()
        if db_path.exists():
            db_path.unlink()
