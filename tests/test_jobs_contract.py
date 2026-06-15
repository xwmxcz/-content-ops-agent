import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.jobs.runner import run_job_async
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


def test_cancel_job_marks_queued_job_cancelled():
    db_path = Path("data/test_jobs_cancel.db")
    if db_path.exists():
        db_path.unlink()
    store = ContentStore(db_path=str(db_path))
    app.dependency_overrides[get_store] = lambda: store
    job = store.create_job(
        job_id="job_cancel_me",
        job_type="content_generation",
        payload={"topic": "测试主题", "content_type": "xiaohongshu", "provider": "siliconflow"},
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )

    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/jobs/{job['id']}")
            missing = client.delete("/api/jobs/job_missing")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["progress"] == 100
        assert body["error"] == "Cancelled by user"
        assert body["completed_at"] is not None

        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
        store.engine.dispose()
        if db_path.exists():
            db_path.unlink()


def test_runner_does_not_overwrite_cancelled_job(monkeypatch):
    db_path = Path("data/test_jobs_cancel_race.db")
    if db_path.exists():
        db_path.unlink()
    store = ContentStore(db_path=str(db_path))
    job = store.create_job(
        job_id="job_cancel_race",
        job_type="content_generation",
        payload={"topic": "测试主题", "content_type": "xiaohongshu", "provider": "siliconflow"},
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )

    async def fake_execute_job(job_payload, llm, job_store):
        job_store.update_job(
            job_payload["id"],
            status="cancelled",
            progress=100,
            error="Cancelled by user",
        )
        return {"content": {"id": 123}}

    monkeypatch.setattr("src.jobs.runner.create_litellm_client", lambda: FakeLLMClient())
    monkeypatch.setattr("src.jobs.runner._execute_job", fake_execute_job)

    try:
        asyncio.run(run_job_async(job["id"], store))

        payload = store.get_job(job["id"])
        assert payload["status"] == "cancelled"
        assert payload["result"] is None
        assert payload["error"] == "Cancelled by user"
    finally:
        store.engine.dispose()
        if db_path.exists():
            db_path.unlink()


def test_start_job_does_not_revive_cancelled_job():
    db_path = Path("data/test_jobs_start_cancelled.db")
    if db_path.exists():
        db_path.unlink()
    store = ContentStore(db_path=str(db_path))
    job = store.create_job(
        job_id="job_already_cancelled",
        job_type="content_generation",
        payload={"topic": "测试主题", "content_type": "xiaohongshu", "provider": "siliconflow"},
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )

    try:
        store.update_job(job["id"], status="cancelled", progress=100, error="Cancelled by user")

        started = store.start_job(job["id"], attempts=1)
        payload = store.get_job(job["id"])

        assert started is None
        assert payload["status"] == "cancelled"
        assert payload["attempts"] == 0
    finally:
        store.engine.dispose()
        if db_path.exists():
            db_path.unlink()
