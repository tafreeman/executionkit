"""Core value types for ExecutionKit.

All value types use ``@dataclass(frozen=True, slots=True)`` for immutability
and memory efficiency.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, TypeVar

from executionkit._constants import DEFAULT_TOOL_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

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

    def __sub__(self, other: TokenUsage) -> TokenUsage:
        """Return the field-wise difference ``self - other``.

        Useful for computing the delta between two :class:`CostTracker`
        snapshots (e.g. per-step cost attribution).  No clamping is applied,
        so callers that subtract a later snapshot from an earlier one can
        observe negative fields.
        """
        return TokenUsage(
            input_tokens=self.input_tokens - other.input_tokens,
            output_tokens=self.output_tokens - other.output_tokens,
            llm_calls=self.llm_calls - other.llm_calls,
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
# StreamingPatternResult
# ---------------------------------------------------------------------------


def _empty_usage() -> TokenUsage:
    """Default usage source for a result whose stream has not been drained."""
    return TokenUsage()


@dataclass(frozen=True, slots=True)
class StreamingPatternResult:
    """Result of a streaming pattern call — text delivered as live deltas.

    Unlike :class:`PatternResult`, the output arrives incrementally through
    :attr:`text_stream`, an async iterator of text chunks. Token usage is only
    known once the provider emits its final usage frame, so :attr:`cost` is
    **not** meaningful until ``text_stream`` has been fully consumed; reading it
    earlier returns whatever has been recorded so far (typically zero).

    The object itself is immutable — :attr:`cost` is a live view over the
    originating cost tracker rather than a stored snapshot, which is how a
    frozen result can surface usage that is populated only after the stream
    drains.
    """

    text_stream: AsyncIterator[str]
    metadata: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    # Callable indirection (rather than a stored TokenUsage) lets a frozen
    # result reflect usage recorded *after* construction, once the stream is
    # drained. Defaults to an empty snapshot for directly-constructed results.
    _usage_source: Callable[[], TokenUsage] = _empty_usage

    @property
    def cost(self) -> TokenUsage:
        """Token usage recorded so far — accurate once the stream is drained."""
        return self._usage_source()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tool:
    """Describes a tool available for LLM tool-calling.

    ``parameters`` is a JSON Schema mapping describing the function arguments.
    Automatically wrapped in a read-only proxy.
    ``execute`` is the async callable invoked when the LLM requests this tool.
    """

    name: str
    description: str
    parameters: Mapping[str, Any]
    execute: Callable[..., Awaitable[str]]
    timeout: float = DEFAULT_TOOL_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        """Wrap ``parameters`` in a read-only proxy to enforce immutability."""
        if not isinstance(self.parameters, MappingProxyType):
            object.__setattr__(
                self, "parameters", MappingProxyType(dict(self.parameters))
            )

    def to_schema(self) -> dict[str, Any]:
        """Return the OpenAI-compatible function tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
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
# TerminationReason
# ---------------------------------------------------------------------------


class TerminationReason(StrEnum):
    """Why a loop pattern stopped iterating.

    Surfaced in :class:`PatternResult` ``metadata["termination_reason"]`` so
    callers can distinguish a clean finish from an iteration-cap truncation
    without catching exceptions.

    Members:
        NATURAL: The loop reached a stopping condition before the cap
            (e.g. the LLM returned no tool calls in ``react_loop``).
        MAX_ITERATIONS: The iteration cap was reached before the loop
            stopped naturally.  For ``react_loop`` this means the LLM never
            returned a tool-call-free response within ``max_rounds``.
    """

    NATURAL = "natural"
    MAX_ITERATIONS = "max_iterations"


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

Evaluator: TypeAlias = Callable[[str, "LLMProvider"], Awaitable[float]]
"""Async callable that scores a response string on [0.0, 1.0]."""


# ---------------------------------------------------------------------------
# CheckpointCallback
# ---------------------------------------------------------------------------

CheckpointCallback: TypeAlias = Callable[
    [int, dict[str, Any]],
    Awaitable[None] | None,
]
"""Callback invoked at loop checkpoints with ``(index, state)``.

``index`` is the 0-based iteration/round number and ``state`` is a
JSON-serializable snapshot of loop progress.  The callback may be either
synchronous (returning ``None``) or asynchronous (returning an awaitable);
pattern loops await the result when one is returned.  Exceptions raised by
the callback are logged and swallowed so a failing checkpoint never aborts
the loop.
"""
