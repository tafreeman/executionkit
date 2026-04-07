"""Core value types for ExecutionKit.

All value types use ``@dataclass(frozen=True, slots=True)`` for immutability
and memory efficiency.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, TypeVar

if TYPE_CHECKING:
    from executionkit.provider import LLMProvider

T = TypeVar("T")


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Accumulated token and call counts."""

    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            llm_calls=self.llm_calls + other.llm_calls,
        )


# ---------------------------------------------------------------------------
# PatternResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatternResult(Generic[T]):
    """Result returned by every reasoning pattern.

    ``metadata`` keys vary by pattern. Each pattern documents its own keys in its
    function docstring. Do not rely on undocumented keys — they are private.
    """

    value: T
    score: float | None = None
    cost: TokenUsage = field(default_factory=TokenUsage)
    metadata: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __str__(self) -> str:
        return str(self.value)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tool:
    """Describes a tool available for LLM tool-calling.

    ``parameters`` is a JSON Schema dict describing the function arguments.
    ``execute`` is the async callable invoked when the LLM requests this tool.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Awaitable[str]]
    timeout: float = 30.0

    def to_schema(self) -> dict[str, Any]:
        """Return the OpenAI-compatible function tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ---------------------------------------------------------------------------
# VotingStrategy
# ---------------------------------------------------------------------------


class VotingStrategy(StrEnum):
    """Strategy for consensus voting."""

    MAJORITY = "majority"
    UNANIMOUS = "unanimous"


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

Evaluator: TypeAlias = Callable[[str, "LLMProvider"], Awaitable[float]]
"""Async callable that scores a response string on [0.0, 1.0]."""
