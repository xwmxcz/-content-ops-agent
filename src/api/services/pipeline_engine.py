"""Persist engine identity with each run so deployment toggles cannot change resumes."""

from typing import Any

from src.api.schemas.agent import PipelineRunRequest
from src.utils import config

ENGINE_REQUEST_KEY = "_pipeline_engine"
SUPPORTED_ENGINES = frozenset({"legacy", "langgraph_v1"})


def stored_pipeline_engine(request_data: dict[str, Any] | None) -> str:
    engine = (request_data or {}).get(ENGINE_REQUEST_KEY, "legacy")
    if not isinstance(engine, str) or engine not in SUPPORTED_ENGINES:
        raise ValueError(f"Unsupported pipeline engine: {engine!r}")
    return engine


def new_pipeline_request(request: PipelineRunRequest) -> dict[str, Any]:
    data = {**request.model_dump(mode="json"), ENGINE_REQUEST_KEY: config.PIPELINE_ENGINE}
    stored_pipeline_engine(data)
    return data
