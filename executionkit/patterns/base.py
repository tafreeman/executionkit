"""Shared pattern utilities: budget-checked completion and score validation."""

from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from executionkit.cost import CostTracker  # noqa: TC001
from executionkit.engine.retry import DEFAULT_RETRY, RetryConfig, with_retry
from executionkit.provider import BudgetExhaustedError, LLMProvider, LLMResponse
from executionkit.types import TokenUsage  # noqa: TC001

BUDGET_EXHAUSTED_SENTINEL = -1

# Maps TokenUsage field names to human-readable labels for error messages.
# Iterating over this dict with getattr() replaces per-field if-chains —
# the same pattern CPython's dataclasses.asdict() uses internally.
# Ref: https://github.com/python/cpython/blob/main/Lib/dataclasses.py
_BUDGET_FIELD_LABELS: dict[str, str] = {
    "llm_calls": "LLM call",
    "input_tokens": "Input token",
    "output_tokens": "Output token",
}


def _check_budget(
    budget: TokenUsage,
    current: TokenUsage,
    fields: tuple[str, ...],
    *,
    sentinel_suffix: str,
    exceeded_suffix: str,
) -> None:
    """Raise :exc:`BudgetExhaustedError` if any tracked field hits its limit.

    Uses ``getattr()`` over named field checks — same pattern as CPython's
    ``dataclasses.asdict()`` — to avoid repeating the check triplet per field.
    A value of ``BUDGET_EXHAUSTED_SENTINEL`` (-1) means the field was fully
    consumed by a prior ``pipe()`` step.

    Args:
        budget: The budget to check against.
        current: Current usage snapshot from :class:`CostTracker`.
        fields: Tuple of :class:`TokenUsage` field names to check.
        sentinel_suffix: Appended to the error message when sentinel found.
        exceeded_suffix: Appended to the error message when limit exceeded.

    Raises:
        BudgetExhaustedError: On the first field that is over budget.
    """
    for field_name in fields:
        label = _BUDGET_FIELD_LABELS[field_name]
        limit = getattr(budget, field_name)
        if limit == BUDGET_EXHAUSTED_SENTINEL:
            raise BudgetExhaustedError(
                f"{label} budget exhausted {sentinel_suffix}",
                cost=current,
                metadata={"budget": budget},
            )
        if limit > 0 and getattr(current, field_name) >= limit:
            raise BudgetExhaustedError(
                f"{label} budget exhausted {exceeded_suffix}",
                cost=current,
                metadata={"budget": budget},
            )


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
        _check_budget(
            budget,
            current,
            tuple(_BUDGET_FIELD_LABELS),
            sentinel_suffix="(forwarded from pipe)",
            exceeded_suffix="before dispatch",
        )

    async def _before_attempt(attempt: int) -> None:
        if attempt > 1 and budget is not None:
            current = tracker.to_usage()
            _check_budget(
                budget,
                current,
                ("llm_calls",),
                sentinel_suffix="before retry (forwarded from pipe)",
                exceeded_suffix="before retry dispatch",
            )
        tracker.reserve_call()

    response = await with_retry(
        provider.complete,
        retry or DEFAULT_RETRY,
        messages,
        _before_attempt=_before_attempt,
        **kwargs,
    )
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

    @property
    def supports_tools(self) -> bool:
        """Delegate capability flag to the wrapped provider.

        A wrapper must not unconditionally claim tool support — it should
        reflect what the inner provider actually supports.
        Ref F-04: https://github.com/BerriAI/litellm/issues/11370 (real-world
        failure from hardcoding capability instead of delegating).
        NOTE (F-01 verified): CostTracker._calls is never accessed directly
        here. reserve_call() and release_call() are the only public API used.
        See executionkit/cost.py.
        """
        return getattr(self._provider, "supports_tools", False)

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
