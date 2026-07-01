from __future__ import annotations

from langchain_core.messages import AIMessage
import pytest

from src.api.services.intent_recognizer import IntentRecognizer


class ScriptedIntentModel:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, messages):
        return AIMessage(content=self.content)


class ScriptedIntentFactory:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def __call__(self, provider, model, temperature, max_tokens):
        self.calls.append({
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return ScriptedIntentModel(self.content)


async def _recognize(factory_content: str, message: str, history: list[dict] | None = None):
    recognizer = IntentRecognizer(ScriptedIntentFactory(factory_content))
    return await recognizer.recognize(
        message=message,
        history=history or [],
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )


@pytest.mark.asyncio
async def test_rule_matches_performance_review():
    intent = await _recognize('{"name":"unknown","confidence":0.9,"slots":{},"clarification":null}', "帮我看看哪些内容值得优化")
    assert intent.name == "performance_review"
    assert "find_optimization_candidates" in intent.allowed_tools


@pytest.mark.asyncio
async def test_llm_json_parse_supports_topic_strategy():
    intent = await _recognize(
        '{"name":"topic_strategy","confidence":0.88,"slots":{"audience":"creators"},"clarification":null}',
        "I need a strategy direction for next week",
    )
    assert intent.name == "topic_strategy"
    assert intent.slots["audience"] == "creators"
    assert "propose_topics" in intent.allowed_tools


@pytest.mark.asyncio
async def test_low_confidence_falls_back_to_clarify():
    intent = await _recognize(
        '{"name":"content_refine","confidence":0.21,"slots":{},"clarification":null}',
        "帮我处理一下这篇",
    )
    assert intent.name == "clarify"
    assert intent.allowed_tools == []
    assert intent.clarification


@pytest.mark.asyncio
async def test_confirmation_becomes_schedule_commit_with_prior_plan():
    recognizer = IntentRecognizer(ScriptedIntentFactory('{"name":"unknown","confidence":0.8,"slots":{},"clarification":null}'))
    history = [
        {
            "role": "assistant",
            "content": "这是发布计划，请确认。",
            "intent": {
                "name": "schedule_propose",
                "confidence": 0.95,
                "slots": {},
                "requires_confirmation": False,
                "allowed_tools": ["list_recent_contents", "search_history", "view_calendar", "propose_publishing_schedule"],
                "route_surface": "chat",
                "route_reason": None,
                "clarification": None,
            },
            "tool_events": [
                {
                    "name": "propose_publishing_schedule",
                    "status": "completed",
                    "output": '{"plan":[{"content_id":7,"platform":"xiaohongshu","scheduled_date":"2026-06-20"}],"committed":false}',
                }
            ],
        }
    ]
    intent = await recognizer.recognize(
        message="好的，开始排吧",
        history=history,
        provider="siliconflow",
        model="Qwen/Qwen2.5-7B-Instruct",
    )
    assert intent.name == "schedule_commit"
    assert intent.allowed_tools == ["commit_publishing_schedule"]
    assert intent.slots["proposal_plan"][0]["content_id"] == 7
