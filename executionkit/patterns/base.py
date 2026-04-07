"""Shared pattern utilities: budget-checked completion and score validation."""

from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

from executionkit.cost import CostTracker  # noqa: TC001
from executionkit.engine.retry import DEFAULT_RETRY, RetryConfig, with_retry
from executionkit.provider import BudgetExhaustedError, LLMProvider, LLMResponse
from executionkit.types import TokenUsage  # noqa: TC001


def validate_score(score: float) -> float:
    """Validate that an evaluator score is in [0.0, 1.0] and not NaN.

    Args:
        score: The score to validate.

    Returns:
        The validated score (unchanged).

    Raises:
        ValueError: If the score is NaN or outside [0.0, 1.0].
    """
    if math.isnan(score) or not (0.0 <= score <= 1.0):
        raise ValueError(f"Invalid evaluator score: {score}")
    return score


async def checked_complete(
    provider: LLMProvider,
    messages: Sequence[dict[str, Any]],
    tracker: CostTracker,
    budget: TokenUsage | None,
    retry: RetryConfig | None,
    **kwargs: Any,
) -> LLMResponse:
    """Budget check, retry-wrapped ``complete()``, and usage recording.

    Performs three steps in order:
    1. Check whether the token/call budget has been exhausted.
    2. Call ``provider.complete()`` wrapped in ``with_retry()``.
    3. Record the response usage on the tracker.

    Args:
        provider: LLM provider to call.
        messages: Chat messages to send.
        tracker: Cost tracker to record usage.
        budget: Optional token/call budget. ``None`` means unlimited.
        retry: Retry configuration. Uses ``DEFAULT_RETRY`` if ``None``.
        **kwargs: Additional arguments forwarded to ``provider.complete()``.

    Returns:
        The LLM response.

    Raises:
        BudgetExhaustedError: If the budget has been exceeded before the call.
        asyncio.CancelledError: Always propagated (via ``with_retry``).
    """
    if budget is not None:
        current = tracker.to_usage()
        if budget.llm_calls > 0 and current.llm_calls >= budget.llm_calls:
            raise BudgetExhaustedError(
                "LLM call budget exhausted before dispatch",
                cost=current,
                metadata={"budget": budget},
            )
        if budget.input_tokens > 0 and current.input_tokens >= budget.input_tokens:
            raise BudgetExhaustedError(
                "Input token budget exhausted before dispatch",
                cost=current,
                metadata={"budget": budget},
            )
        if budget.output_tokens > 0 and current.output_tokens >= budget.output_tokens:
            raise BudgetExhaustedError(
                "Output token budget exhausted before dispatch",
                cost=current,
                metadata={"budget": budget},
            )
    # Reserve the call slot BEFORE yielding to the event loop (P0-3: TOCTOU fix).
    # If the HTTP call fails, the slot is released so it does not distort budget.
    tracker.reserve_call()
    try:
        response = await with_retry(
            provider.complete,
            retry or DEFAULT_RETRY,
            messages,
            **kwargs,
        )
    except Exception:
        tracker.release_call()  # release reserved slot on failure
        raise
    tracker.record_without_call(response)
    return response


def _note_truncation(
    response: LLMResponse, metadata: dict[str, Any], context: str
) -> None:
    """Increment truncated_responses counter and emit a warning if truncated.

    Args:
        response: The LLM response to inspect.
        metadata: The pattern's running metadata dict (mutated in place).
        context: Pattern name for the warning message.
    """
    if not response.was_truncated:
        return
    metadata["truncated_responses"] = int(metadata.get("truncated_responses", 0)) + 1
    warnings.warn(
        f"{context} returned a truncated response "
        f"(finish_reason={response.finish_reason!r})",
        stacklevel=3,
    )


class _TrackedProvider:
    """Wraps an ``LLMProvider`` to auto-apply budget, retry, and truncation tracking.

    Used by patterns (e.g. ``refine_loop``) that need to call the provider
    multiple times while sharing a single ``CostTracker`` and metadata dict.
    """

    supports_tools: Literal[True] = True

    def __init__(
        self,
        provider: LLMProvider,
        tracker: CostTracker,
        metadata: dict[str, Any],
        *,
        budget: TokenUsage | None,
        retry: RetryConfig | None,
        context: str,
    ) -> None:
        self._provider = provider
        self._tracker = tracker
        self._metadata = metadata
        self._budget = budget
        self._retry = retry
        self._context = context

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Delegate to ``checked_complete`` and call ``_note_truncation``."""
        response = await checked_complete(
            self._provider,
            messages,
            self._tracker,
            self._budget,
            self._retry,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            **kwargs,
        )
        _note_truncation(response, self._metadata, self._context)
        return response
