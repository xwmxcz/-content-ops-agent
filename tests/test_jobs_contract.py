import asyncio
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from src.api.dependencies import get_store
from src.api.main import app
from src.jobs.runner import run_job_async


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


def test_content_generation_job_completes(store, monkeypatch):
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


def test_agent_run_job_completes(store, monkeypatch):
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


def test_job_capacity_limit_returns_429(store, monkeypatch):
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


def test_cancel_job_marks_queued_job_cancelled(store):
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


def test_runner_does_not_overwrite_cancelled_job(store, monkeypatch):
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

    asyncio.run(run_job_async(job["id"], store))

    payload = store.get_job(job["id"])
    assert payload["status"] == "cancelled"
    assert payload["result"] is None
    assert payload["error"] == "Cancelled by user"


def test_start_job_does_not_revive_cancelled_job(store):
    job = store.create_job(
        job_id="job_already_cancelled",
        job_type="content_generation",
        payload={"topic": "测试主题", "content_type": "xiaohongshu", "provider": "siliconflow"},
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )

    store.update_job(job["id"], status="cancelled", progress=100, error="Cancelled by user")

    started = store.start_job(job["id"], attempts=1)
    payload = store.get_job(job["id"])

    assert started is None
    assert payload["status"] == "cancelled"
    assert payload["attempts"] == 0


def test_waiting_retry_is_visible_and_can_be_cancelled(store):
    job = store.create_job("job_retry_cancel", "titles", {"topic": "test"})
    store.update_job(
        job["id"],
        status="failed",
        attempts=1,
        max_retries=3,
        error_type="transient",
        next_retry_at=datetime.now() + timedelta(minutes=1),
    )
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as client:
            pending = client.get(f"/api/jobs/{job['id']}").json()
            cancelled = client.delete(f"/api/jobs/{job['id']}").json()
    finally:
        app.dependency_overrides.clear()

    assert pending["next_retry_at"] is not None
    assert pending["max_retries"] == 3
    assert pending["error_type"] == "transient"
    assert cancelled["status"] == "cancelled"
    assert cancelled["next_retry_at"] is None
    asyncio.run(run_job_async(job["id"], store))
    assert store.get_job(job["id"])["attempts"] == 1


def test_cancellation_leaves_permanent_failure_and_completed_jobs_unchanged(store):
    for status in ("failed", "completed"):
        job_id = f"job_terminal_{status}"
        store.create_job(job_id, "titles", {"topic": "test"})
        store.update_job(job_id, status=status, result={"text": "original"}, error="original")

        result = store.cancel_job(job_id)

        assert result["status"] == status
        assert result["result"] == {"text": "original"}
        assert result["error"] == "original"


def test_guarded_worker_update_cannot_overwrite_cancellation_or_new_owner(store):
    store.create_job("job_guard", "titles", {"topic": "test"})
    store.update_job("job_guard", status="running", worker_id="original")
    store.cancel_job("job_guard")

    assert (
        store.update_job(
            "job_guard",
            expected_statuses={"running"},
            expected_worker_id="original",
            status="completed",
            result={"text": "late result"},
        )
        is None
    )
    assert store.get_job("job_guard")["status"] == "cancelled"

    store.update_job("job_guard", status="running", worker_id="replacement")
    assert (
        store.update_job(
            "job_guard",
            expected_statuses={"running"},
            expected_worker_id="original",
            status="failed",
            error="late error",
        )
        is None
    )
    assert store.get_job("job_guard")["status"] == "running"


def test_starting_retry_clears_previous_attempt_failure_metadata(store):
    store.create_job("job_retry_start", "titles", {"topic": "test"})
    store.update_job(
        "job_retry_start",
        status="failed",
        error="timeout",
        error_type="transient",
        next_retry_at=datetime.now() - timedelta(seconds=1),
    )

    started = store.start_job("job_retry_start", attempts=2)

    assert started["status"] == "running"
    assert started["error"] is None
    assert started["error_type"] is None
    assert started["next_retry_at"] is None
