"""Manual smoke test: run the researcher sub-agent against DeepSeek.

Verifies:
  1. No UserWarning about `extra_body` being passed via `model_kwargs`.
  2. The tool-calling loop completes and returns non-empty text.

Run:
    python tests/manual_deepseek_researcher.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.api.schemas.agent import SubAgentId  # noqa: E402
from src.api.services.sub_agents import SUB_AGENTS, SubAgentRunner  # noqa: E402
from src.storage import ContentStore  # noqa: E402
from src.utils import config  # noqa: E402


async def main() -> int:
    provider = "deepseek"
    if not config.get_api_key(provider):
        print("[skip] DEEPSEEK_API_KEY not set")
        return 0

    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    spec = SUB_AGENTS["researcher"]

    # Use an in-memory SQLite store so we don't touch the real data dir.
    store = ContentStore(database_url="sqlite:///:memory:")
    runner = SubAgentRunner(store=store)

    tool_events: list[tuple[str, dict]] = []

    async def tool_sink(name: str, payload: dict) -> None:
        tool_events.append((name, payload))

    user_prompt = (
        "Topic: AI Agent observability best practices in 2026. "
        "Briefly research and return 5-8 bullet points the writer should know."
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        text, p_tok, c_tok, _, cost = await runner.run(
            spec=spec,
            user_prompt=user_prompt,
            provider=provider,
            model=model,
            max_tokens=1024,
            tool_sink=tool_sink,
        )

    extra_body_warns = [
        w for w in caught if "extra_body" in str(w.message)
    ]

    print("=" * 60)
    print(f"provider={provider} model={model}")
    print(f"prompt_tokens={p_tok} completion_tokens={c_tok} est_cost=${cost}")
    print(f"tool_events={len(tool_events)}: {[e[0] for e in tool_events]}")
    print(f"extra_body warnings: {len(extra_body_warns)}")
    print("-" * 60)
    print(text[:1200])
    print("=" * 60)

    if extra_body_warns:
        for w in extra_body_warns:
            print(f"[WARN] {w.message}")
        return 1
    if not text.strip():
        print("[FAIL] empty text from researcher")
        return 2
    print("[OK] no extra_body warning, researcher returned content")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
