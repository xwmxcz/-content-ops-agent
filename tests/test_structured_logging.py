import json
import logging

from src.utils.structured_logging import JsonFormatter


def test_json_formatter_emits_correlation_fields_without_traceback_text():
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="job_failed",
        args=(),
        exc_info=None,
    )
    record.event = "job_failed"
    record.request_id = "req_123"
    record.job_id = "job_456"
    record.error_class = "TimeoutError"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "job_failed"
    assert payload["request_id"] == "req_123"
    assert payload["job_id"] == "job_456"
    assert payload["error_class"] == "TimeoutError"
    assert "password" not in json.dumps(payload).lower()
