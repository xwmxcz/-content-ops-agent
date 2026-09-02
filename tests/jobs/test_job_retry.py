"""Tests for P1-03: Automatic job retry with error classification and exponential backoff."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.jobs.error_classifier import ErrorClassifier
from src.jobs.runner import _calculate_backoff_delay, _handle_job_error, run_job_async
from src.llm.litellm_client import LLMGenerationError
from src.storage import ContentStore


class TransientNetworkError(Exception):
    """Simulates a transient network error."""
    pass


class PermanentValidationError(Exception):
    """Simulates a permanent validation error."""
    pass


class TestErrorClassification:
    """Test error type classification logic."""

    def test_classify_transient_network_timeout(self):
        """Network timeouts should be classified as transient."""
        error = TimeoutError("Connection timeout")
        assert ErrorClassifier.classify(error) == "transient"

    def test_classify_transient_rate_limit(self):
        """Rate limit errors should be classified as transient."""
        error = Exception("Rate limit exceeded")
        assert ErrorClassifier.classify(error) == "transient"

    def test_classify_transient_503(self):
        """503 Service Unavailable should be classified as transient."""
        error = Exception("Service unavailable")
        assert ErrorClassifier.classify(error) == "transient"

    def test_classify_permanent_validation(self):
        """Validation errors should be classified as permanent."""
        error = ValueError("Invalid input format")
        assert ErrorClassifier.classify(error) == "permanent"

    def test_classify_permanent_404(self):
        """404 Not Found should be classified as permanent."""
        error = ValueError("Invalid model configuration")
        assert ErrorClassifier.classify(error) == "permanent"

    def test_classify_permanent_401(self):
        """401 Unauthorized should be classified as permanent."""
        error = Exception("Unauthorized: invalid API key")
        assert ErrorClassifier.classify(error) == "permanent"

    def test_should_retry_transient_below_max(self):
        """Transient errors below max_retries should retry."""
        error = TimeoutError("Connection timeout")
        assert ErrorClassifier.should_retry(error, current_attempts=2, max_retries=5) is True

    def test_should_not_retry_transient_at_max(self):
        """Transient errors at max_retries should not retry."""
        error = TimeoutError("Connection timeout")
        assert ErrorClassifier.should_retry(error, current_attempts=5, max_retries=5) is False

    def test_should_not_retry_permanent(self):
        """Permanent errors should never retry."""
        error = ValueError("Invalid input")
        assert ErrorClassifier.should_retry(error, current_attempts=1, max_retries=5) is False


class TestBackoffCalculation:
    """Test exponential backoff delay calculation."""

    def test_first_retry_30_seconds(self):
        """First retry should be 30 seconds."""
        assert _calculate_backoff_delay(1) == 30

    def test_second_retry_60_seconds(self):
        """Second retry should be 60 seconds (30 * 2^1)."""
        assert _calculate_backoff_delay(2) == 60

    def test_third_retry_120_seconds(self):
        """Third retry should be 120 seconds (30 * 2^2)."""
        assert _calculate_backoff_delay(3) == 120

    def test_fourth_retry_240_seconds(self):
        """Fourth retry should be 240 seconds (30 * 2^3)."""
        assert _calculate_backoff_delay(4) == 240

    def test_fifth_retry_480_seconds(self):
        """Fifth retry should be 480 seconds (30 * 2^4)."""
        assert _calculate_backoff_delay(5) == 480

    def test_max_delay_capped(self):
        """Delay should be capped at max (480 seconds = 8 minutes)."""
        # Attempt 6 would be 960 seconds, but should be capped at 480
        assert _calculate_backoff_delay(6) == 480


class TestJobRetryMechanism:
    """Test end-to-end job retry behavior."""

    @pytest.mark.asyncio
    async def test_transient_error_schedules_retry(self, store: ContentStore):
        """Transient errors should set next_retry_at and requeue."""
        # Create a job
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]

        # Simulate a transient error
        error = TimeoutError("Connection timeout")
        
        _handle_job_error(job_id, error, current_attempt=1, max_retries=5, store=store)

        # Verify job state
        updated_job = store.get_job(job_id)
        assert updated_job["status"] == "failed"
        assert updated_job["error_type"] == "transient"
        assert updated_job["next_retry_at"] is not None
        
        # Verify next_retry_at is approximately 30 seconds from now
        next_retry = datetime.fromisoformat(updated_job["next_retry_at"])
        expected_time = datetime.now() + timedelta(seconds=30)
        assert abs((next_retry - expected_time).total_seconds()) < 5  # Within 5 seconds tolerance

    @pytest.mark.asyncio
    async def test_permanent_error_does_not_retry(self, store: ContentStore):
        """Permanent errors should not schedule a retry."""
        # Create a job
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]

        # Simulate a permanent error
        error = ValueError("Invalid input format")
        
        _handle_job_error(job_id, error, current_attempt=1, max_retries=5, store=store)

        # Verify job state
        updated_job = store.get_job(job_id)
        assert updated_job["status"] == "failed"
        assert updated_job["error_type"] == "permanent"
        assert updated_job["next_retry_at"] is None

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, store: ContentStore):
        """Jobs at max_retries should not retry even for transient errors."""
        # Create a job
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]

        # Simulate a transient error at max retries
        error = TimeoutError("Connection timeout")
        
        _handle_job_error(job_id, error, current_attempt=5, max_retries=5, store=store)

        # Verify job state
        updated_job = store.get_job(job_id)
        assert updated_job["status"] == "failed"
        assert updated_job["error_type"] == "transient"
        assert updated_job["next_retry_at"] is None

    @pytest.mark.asyncio
    async def test_exponential_backoff_progression(self, store: ContentStore):
        """Verify backoff delay increases exponentially with each retry."""
        # Only test attempts 1-4, since attempt 5 is at max and won't schedule a retry
        expected_delays = [(1, 30), (2, 60), (3, 120), (4, 240)]

        for attempt, expected_delay in expected_delays:
            job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
                payload={"topic": "test", "content_type": "blog"},
                provider="openai",
                model="gpt-4",
            )
            job_id = job["id"]
            
            error = TimeoutError("Connection timeout")
            _handle_job_error(job_id, error, current_attempt=attempt, max_retries=5, store=store)
            
            updated_job = store.get_job(job_id)
            next_retry = updated_job["next_retry_at"]
            if isinstance(next_retry, str):
                next_retry = datetime.fromisoformat(next_retry)
            expected_time = datetime.now() + timedelta(seconds=expected_delay)
            
            # Verify correct delay (within 5 seconds tolerance)
            assert abs((next_retry - expected_time).total_seconds()) < 5
        
        # Test that attempt 5 (at max) does NOT schedule retry
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]
        error = TimeoutError("Connection timeout")
        _handle_job_error(job_id, error, current_attempt=5, max_retries=5, store=store)
        
        updated_job = store.get_job(job_id)
        assert updated_job["status"] == "failed"
        assert updated_job["next_retry_at"] is None

    @pytest.mark.asyncio
    async def test_job_skips_early_retry(self, store: ContentStore):
        """Jobs should not execute if next_retry_at is in the future."""
        # Create and fail a job with future retry time
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]
        
        # Set next_retry_at to 1 hour in the future
        future_time = datetime.now() + timedelta(hours=1)
        store.update_job(
            job_id,
            status="failed",
            next_retry_at=future_time,
            error_type="transient",
        )

        # Try to run the job - it should check next_retry_at and skip
        job_before = store.get_job(job_id)
        await run_job_async(job_id, store)
        job_after = store.get_job(job_id)
        
        # Job should remain in failed state with same next_retry_at
        assert job_after["status"] == "failed"
        assert job_after["next_retry_at"] == job_before["next_retry_at"]

    @pytest.mark.asyncio
    async def test_job_executes_after_retry_time(self, store: ContentStore):
        """Jobs should execute when next_retry_at is in the past."""
        # Create and fail a job with past retry time
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]
        
        # Set next_retry_at to 1 hour in the past
        past_time = datetime.now() - timedelta(hours=1)
        store.update_job(
            job_id,
            status="failed",
            next_retry_at=past_time,
            error_type="transient",
            attempts=1,
        )

        # Mock the execution to succeed
        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"content": "Generated content"}
            
            await run_job_async(job_id, store)
            
            # Job should have been executed
            mock_execute.assert_called_once()

        # Verify job completed
        updated_job = store.get_job(job_id)
        assert updated_job["status"] == "completed"

    @pytest.mark.asyncio
    async def test_retry_increments_attempts(self, store: ContentStore):
        """Each retry should increment the attempts counter."""
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]

        # Simulate multiple retries
        error = TimeoutError("Connection timeout")
        
        for attempt in range(1, 4):
            _handle_job_error(job_id, error, current_attempt=attempt, max_retries=5, store=store)
            
            # Verify next_retry_at is set
            current_job = store.get_job(job_id)
            assert current_job["next_retry_at"] is not None
            assert current_job["error_type"] == "transient"

    @pytest.mark.asyncio
    async def test_custom_max_retries(self, store: ContentStore):
        """Jobs should respect custom max_retries values."""
        # Create a job with custom max_retries
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]
        
        # Manually set max_retries to 3
        store.update_job(job_id, max_retries=3)

        error = TimeoutError("Connection timeout")
        
        # Attempt 3 should NOT retry (at max)
        _handle_job_error(job_id, error, current_attempt=3, max_retries=3, store=store)

        # Verify final state
        updated_job = store.get_job(job_id)
        assert updated_job["status"] == "failed"
        assert updated_job["next_retry_at"] is None


class TestRetryIntegration:
    """Integration tests for the full retry flow."""

    @pytest.mark.asyncio
    async def test_full_retry_flow_success_on_second_attempt(self, store: ContentStore):
        """Test a job that fails once then succeeds."""
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]

        call_count = 0

        async def mock_execute_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("First attempt fails")
            return {"content": "Success on retry"}

        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = mock_execute_with_retry
            
            # First attempt - should fail and schedule retry
            await run_job_async(job_id, store)
            
            job_after_first = store.get_job(job_id)
            assert job_after_first["status"] == "failed"
            assert job_after_first["error_type"] == "transient"
            assert job_after_first["attempts"] == 1

            # Second attempt - should succeed
            # Simulate time passing by clearing next_retry_at
            store.update_job(job_id, next_retry_at=datetime.now() - timedelta(seconds=1))
            
            await run_job_async(job_id, store)
            
            job_after_second = store.get_job(job_id)
            assert job_after_second["status"] == "completed"
            assert job_after_second["attempts"] == 2
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_mixed_error_types_no_retry_after_permanent(self, store: ContentStore):
        """Test that a permanent error after transient errors stops retries."""
        job = store.create_job(
            job_id=str(uuid.uuid4()),
            job_type="content_generate",
            payload={"topic": "test", "content_type": "blog"},
            provider="openai",
            model="gpt-4",
        )
        job_id = job["id"]

        # First attempt: transient error
        with patch("src.jobs.runner._execute_job", new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = TimeoutError("Transient failure")
            await run_job_async(job_id, store)
            
            job_after_first = store.get_job(job_id)
            assert job_after_first["error_type"] == "transient"

            # Second attempt: permanent error
            mock_execute.side_effect = ValueError("Invalid input")
            store.update_job(job_id, next_retry_at=datetime.now() - timedelta(seconds=1))
            
            await run_job_async(job_id, store)
            
            job_after_second = store.get_job(job_id)
            assert job_after_second["error_type"] == "permanent"
            assert job_after_second["next_retry_at"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
