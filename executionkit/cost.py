"""Cost tracking for LLM calls.

``CostTracker`` accumulates token usage across multiple LLM calls and
produces a ``TokenUsage`` snapshot on demand.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from executionkit.types import TokenUsage

if TYPE_CHECKING:
    from executionkit.provider import LLMResponse


class CostTracker:
    """Mutable accumulator for token and call counts."""

    def __init__(self) -> None:
        self._input: int = 0
        self._output: int = 0
        self._calls: int = 0

    def record(self, response: LLMResponse) -> None:
        """Record usage from a single LLM response."""
        self._input += response.input_tokens
        self._output += response.output_tokens
        self._calls += 1

    def reserve_call(self) -> None:
        """Reserve a call slot before dispatching (for TOCTOU-safe budget checks).

        Called by :func:`checked_complete` before awaiting the provider call.
        If the call fails, use :meth:`release_call` to undo the reservation.
        """
        self._calls += 1

    def release_call(self) -> None:
        """Release a reserved call slot (after a failed call).

        Only call this after :meth:`reserve_call` if the provider call raised
        an exception and did not complete successfully.
        """
        self._calls -= 1

    def record_without_call(self, response: LLMResponse) -> None:
        """Record token usage from a response without incrementing the call counter.

        Used by :func:`checked_complete` which pre-increments ``_calls`` before
        the ``await`` to prevent TOCTOU races in concurrent budget checks.
        """
        self._input += response.input_tokens
        self._output += response.output_tokens

    @property
    def call_count(self) -> int:
        """Number of LLM calls recorded so far."""
        return self._calls

    def add_usage(self, usage: TokenUsage) -> None:
        """Add pre-computed usage to the tracker (e.g. from a pattern result).

        Use this instead of accessing private fields directly.
        """
        self._input += usage.input_tokens
        self._output += usage.output_tokens
        self._calls += usage.llm_calls

    @property
    def total_tokens(self) -> int:
        """Total input + output tokens recorded so far."""
        return self._input + self._output

    def to_usage(self) -> TokenUsage:
        """Return an immutable snapshot of accumulated usage."""
        return TokenUsage(
            input_tokens=self._input,
            output_tokens=self._output,
            llm_calls=self._calls,
        )
