"""Pluggable in-session context engine (Hermes layer 4).

Defines the abstract base class; the default implementation lives in
`context_compressor.py`. Engines are stateless w.r.t. the agent and operate
on the in-memory `BaseMessage` list passed each turn.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage


@dataclass
class CompressionResult:
    """Returned by `ContextEngine.maybe_compress`.

    `messages` is the (possibly compressed) message list to feed to the model.
    `compressed` indicates whether compression actually fired this turn; the
    chat agent surfaces this via tool_events for the UI. `summary` is the
    human-readable summary inserted in place of the middle slice when
    compression fires (or None when it did not).
    """

    messages: list[BaseMessage]
    compressed: bool
    summary: str | None = None
    dropped_count: int = 0


class ContextEngine(ABC):
    """Hook called once per agent turn before the model is invoked."""

    @abstractmethod
    async def maybe_compress(
        self,
        messages: list[BaseMessage],
        *,
        provider: str,
        model: str,
        extra: dict[str, Any] | None = None,
    ) -> CompressionResult:
        """Return `messages` unchanged or a shorter list with a summary insert."""
        raise NotImplementedError
