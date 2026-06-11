"""Cost tracking for LLM calls.

``CostTracker`` accumulates token usage across multiple LLM calls and
produces a ``TokenUsage`` snapshot on demand.

Concurrency model
-----------------
``CostTracker`` is **NOT thread-safe**.  Its counters are plain Python
``int`` attributes with no locking.  Under ``threading``, multiple threads
can race past budget checks and cause the budget to be overshot.

For asyncio (cooperative scheduling), ``CostTracker`` is safe **only when
the budget check and the subsequent ``reserve_call()`` execute within the
same synchronous run-segment** — i.e. without an ``await`` between them.
:func:`~executionkit.patterns.base.checked_complete` upholds this invariant
by design (see that function's ``_before_attempt`` closure): the check and
``reserve_call()`` are co-located with no ``await`` between them, so no
other coroutine can be scheduled between the two operations.

If this code is ever refactored to insert an ``await`` between
``_check_budget`` and ``reserve_call()``, the budget guarantee breaks.  A
CI test in ``tests/test_patterns.py`` (``test_no_await_between_check_and_reserve``)
uses ``inspect.getsource`` to assert this invariant is preserved.
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
        """Reserve a call slot before dispatching (for budget-safe accounting).

        Called by :func:`~executionkit.patterns.base.checked_complete` before
        awaiting the provider call.  Reservations intentionally count every
        wire attempt, including failed attempts, so call budgets cap retries
        as well as successes.

        **Concurrency contract**: this method must be called in the same
        synchronous run-segment as the preceding budget check — with no
        ``await`` between them — to prevent concurrent asyncio coroutines
        from racing past the check.  See module-level docstring for details.
        This guarantee does NOT hold under threading.
        """
        self._calls += 1

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
