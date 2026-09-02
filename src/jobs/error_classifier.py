"""Error classification for job retry logic.

Categorizes exceptions into transient (retriable) vs permanent (non-retriable) errors
to enable smart automatic retries with exponential backoff.
"""
from __future__ import annotations

import httpx


class ErrorClassifier:
    """Classifies exceptions as transient or permanent for retry decisions."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"

    @classmethod
    def classify(cls, exc: Exception) -> str:
        """Return 'transient' if the error is retriable, 'permanent' otherwise.

        Transient errors include:
        - Network timeouts and connection errors
        - HTTP 429 (rate limit), 503 (service unavailable), 502/504 (gateway errors)
        - Temporary service unavailability
        - Database connection errors (not integrity/constraint violations)

        Permanent errors include:
        - Configuration errors (missing API keys, invalid config)
        - Validation errors (bad request data)
        - HTTP 4xx (except 429)
        - Business logic errors
        - Permission/authorization errors
        - Data integrity violations
        """
        exc_class_name = exc.__class__.__name__
        exc_message = str(exc).lower()

        # Configuration errors are permanent
        if "LLMConfigurationError" in exc_class_name:
            return cls.PERMANENT
        if "ConfigurationError" in exc_class_name:
            return cls.PERMANENT
        if "api key" in exc_message or "api_key" in exc_message:
            return cls.PERMANENT

        # Validation errors are permanent
        if "ValidationError" in exc_class_name:
            return cls.PERMANENT
        if "PublicationValidationError" in exc_class_name:
            return cls.PERMANENT
        if isinstance(exc, ValueError):
            return cls.PERMANENT

        # LookupError (KeyError, IndexError) usually means missing required data - permanent
        if isinstance(exc, LookupError):
            return cls.PERMANENT

        # HTTP errors: check status codes
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            # Rate limit and server errors are transient
            if status in {429, 502, 503, 504}:
                return cls.TRANSIENT
            # 4xx client errors (except 429) are permanent
            if 400 <= status < 500:
                return cls.PERMANENT
            # 5xx server errors (except listed above) are transient
            if 500 <= status < 600:
                return cls.TRANSIENT

        # Network/connection errors are transient
        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
            return cls.TRANSIENT
        if "timeout" in exc_message or "timed out" in exc_message:
            return cls.TRANSIENT
        if "connection" in exc_message and ("refused" in exc_message or "reset" in exc_message or "closed" in exc_message):
            return cls.TRANSIENT

        # LLM generation errors: inspect message for clues
        if "LLMGenerationError" in exc_class_name:
            # Rate limit messages are transient
            if any(keyword in exc_message for keyword in ["rate limit", "too many requests", "quota exceeded"]):
                return cls.TRANSIENT
            # Service unavailable is transient
            if any(keyword in exc_message for keyword in ["service unavailable", "overloaded", "try again"]):
                return cls.TRANSIENT
            # Model/token errors are permanent
            if any(keyword in exc_message for keyword in ["invalid model", "context length", "token limit"]):
                return cls.PERMANENT
            # Default LLM errors to transient (might be temporary provider issues)
            return cls.TRANSIENT

        # MCP client errors: check message
        if "McpClientError" in exc_class_name:
            # Authentication/config issues are permanent
            if any(keyword in exc_message for keyword in ["authentication", "unauthorized", "forbidden", "disabled"]):
                return cls.PERMANENT
            # Timeout/network issues are transient
            if any(keyword in exc_message for keyword in ["timeout", "connection", "network"]):
                return cls.TRANSIENT
            # Default MCP errors to transient
            return cls.TRANSIENT

        # Pipeline execution errors: inspect message
        if "PipelineExecutionError" in exc_class_name:
            # Configuration issues are permanent
            if any(keyword in exc_message for keyword in ["configuration", "invalid", "missing required"]):
                return cls.PERMANENT
            # Otherwise transient (might be temporary LLM issues)
            return cls.TRANSIENT

        # Database errors: only connection errors are transient
        if "OperationalError" in exc_class_name:
            if any(keyword in exc_message for keyword in ["connection", "connect", "server closed"]):
                return cls.TRANSIENT
            # Other operational errors (e.g., disk full, deadlock) are permanent
            return cls.PERMANENT
        if "IntegrityError" in exc_class_name:
            return cls.PERMANENT

        # Default: treat unknown errors as transient to give them a chance to recover
        # This is safer than marking them permanent and losing potentially recoverable work
        return cls.TRANSIENT

    @classmethod
    def should_retry(cls, exc: Exception, current_attempts: int, max_retries: int) -> bool:
        """Return True if the job should be retried based on error type and attempt count."""
        if current_attempts >= max_retries:
            return False
        return cls.classify(exc) == cls.TRANSIENT
