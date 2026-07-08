"""Shared pattern utilities: budget-checked completion and score validation."""

from __future__ import annotations

import inspect
import logging
import math
import warnings
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from executionkit.types import CheckpointCallback

from executionkit.cost import CostTracker  # noqa: TC001
from executionkit.engine.retry import DEFAULT_RETRY, RetryConfig, with_retry
from executionkit.observability import TraceCallback, TraceEvent, emit_trace
from executionkit.provider import (
    BudgetExhaustedError,
    LLMProvider,
    LLMResponse,
    StreamingProvider,
    _redact_sensitive,
)
from executionkit.types import StreamingPatternResult, TokenUsage

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


async def run_checkpoint(
    callback: CheckpointCallback | None,
    index: int,
    state: dict[str, Any],
    *,
    context: str,
) -> None:
    """Invoke a checkpoint callback, awaiting async results and isolating failures.

    Supports both synchronous (``-> None``) and asynchronous
    (``-> Awaitable[None]``) callbacks.  Any exception raised by the callback is
    logged and swallowed so a failing checkpoint never aborts the loop;
    ``asyncio.CancelledError`` (a ``BaseException``, not an ``Exception``) still
    propagates normally.

    Args:
        callback: The user checkpoint callback, or ``None`` (no-op).
        index: 0-based iteration/round index passed to the callback.
        state: JSON-serializable progress snapshot passed to the callback.
        context: Pattern name used in the warning log message.
    """
    if callback is None:
        return
    try:
        result = callback(index, state)
        if inspect.isawaitable(result):
            await result
    except Exception:
        logging.getLogger(__name__).warning(
            "%s checkpoint callback raised; continuing", context, exc_info=True
        )


async def checked_complete(
    provider: LLMProvider,
    messages: Sequence[dict[str, Any]],
    tracker: CostTracker,
    budget: TokenUsage | None,
    retry: RetryConfig | None,
    trace: TraceCallback | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """Budget check, retry-wrapped ``complete()``, and usage recording.

    Performs three steps in order:

    1. Check whether the token/call budget has been exhausted.
    2. Call ``provider.complete()`` wrapped in ``with_retry()``.
    3. Record the response usage on the tracker.

    **Concurrency model**: the budget check and ``reserve_call()`` in
    ``_before_attempt`` are a *no-await critical section* — there is
    deliberately no ``await`` between ``_check_budget`` and
    ``tracker.reserve_call()``.  Under cooperative asyncio scheduling this
    means no other coroutine can be scheduled between the check and the
    reservation, so concurrent coroutines sharing the same ``CostTracker``
    cannot both pass the budget check before either has incremented the
    counter.

    This guarantee relies on cooperative scheduling (single event loop) and
    does **NOT** hold under ``threading``.  See :mod:`executionkit.cost` for
    the full concurrency contract.

    A CI test (``test_no_await_between_check_and_reserve`` in
    ``tests/patterns/test_patterns_common.py``) uses AST inspection to assert that no
    ``await`` is inserted between the two operations.  If that test fails
    after a refactor, the budget safety guarantee must be re-evaluated before
    merging.

    Args:
        provider: LLM provider to call.
        messages: Chat messages to send.
        tracker: Cost tracker to record usage.
        budget: Optional token/call budget. ``None`` means unlimited.
        retry: Retry configuration. Uses ``DEFAULT_RETRY`` if ``None``.
        trace: Optional structured trace callback.
        **kwargs: Additional arguments forwarded to ``provider.complete()``.

    Returns:
        The LLM response.

    Raises:
        BudgetExhaustedError: If the budget has been exceeded before the call.
        asyncio.CancelledError: Always propagated (via ``with_retry``).
    """

    async def _before_attempt(attempt: int) -> None:
        # ---- no-await critical section: check then reserve ----
        # No ``await`` must be inserted between _check_budget and
        # reserve_call().  The asyncio budget-safety guarantee depends on
        # these two operations running in the same synchronous run-segment.
        # See checked_complete() docstring and executionkit/cost.py module
        # docstring for the full concurrency contract.
        # A source-inspection test (test_no_await_between_check_and_reserve)
        # will fail CI if an await is accidentally introduced here.
        if budget is not None:
            current = tracker.to_usage()
            if attempt == 1:
                _check_budget(
                    budget,
                    current,
                    tuple(_BUDGET_FIELD_LABELS),
                    sentinel_suffix="(forwarded from pipe)",
                    exceeded_suffix="before dispatch",
                )
            else:
                _check_budget(
                    budget,
                    current,
                    ("llm_calls",),
                    sentinel_suffix="before retry (forwarded from pipe)",
                    exceeded_suffix="before retry dispatch",
                )
        tracker.reserve_call()
        # ---- end critical section ----
        await emit_trace(
            trace,
            TraceEvent.create(
                "llm_call_start",
                {"attempt": attempt, "cost": tracker.to_usage()},
            ),
        )

    try:
        response = await with_retry(
            provider.complete,
            retry or DEFAULT_RETRY,
            messages,
            _before_attempt=_before_attempt,
            **kwargs,
        )
    except Exception as exc:
        await emit_trace(
            trace,
            TraceEvent.create(
                "llm_call_error",
                {"error_type": type(exc).__name__, "cost": tracker.to_usage()},
            ),
        )
        raise
    tracker.record_without_call(response)
    await emit_trace(
        trace,
        TraceEvent.create(
            "llm_call_end",
            {
                "cost": tracker.to_usage(),
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                # Response bodies can echo credentials supplied in the prompt;
                # redact before the library emits them so a secret in the
                # completion never leaks through the trace callback.
                "content": _redact_sensitive(response.content),
            },
        ),
    )
    return response


async def checked_stream(
    provider: StreamingProvider,
    messages: Sequence[dict[str, Any]],
    tracker: CostTracker,
    budget: TokenUsage | None,
    retry: RetryConfig | None,
    trace: TraceCallback | None = None,
    **kwargs: Any,
) -> StreamingPatternResult:
    """Budget-checked, trace-instrumented streaming completion.

    Parallel to :func:`checked_complete`, but yields live text deltas instead
    of returning a single response.  Before any token is produced it eagerly:

    1. Checks the budget — raises :exc:`BudgetExhaustedError` if exhausted.
    2. Calls ``tracker.reserve_call()`` in the same no-await segment as the
       budget check (same concurrency contract as :func:`checked_complete`).
    3. Emits the ``llm_call_start`` trace event.

    The returned :class:`StreamingPatternResult` wraps the provider stream so
    that, once the caller drains it, token usage is recorded
    (``record_without_call``) and ``llm_call_end`` is emitted.  If the stream
    raises mid-flight, ``llm_call_error`` is emitted and the exception
    propagates to the consumer.

    Retry is **not** supported for streaming — a partial stream cannot be
    replayed — so a non-``None`` *retry* is logged and ignored.

    Args:
        provider: Streaming-capable LLM provider.
        messages: Chat messages to send.
        tracker: Cost tracker to record usage on.
        budget: Optional token/call budget. ``None`` means unlimited.
        retry: Ignored (logged) — streaming cannot be retried.
        trace: Optional structured trace callback.
        **kwargs: Forwarded to ``provider.stream()`` (e.g. ``temperature``).

    Returns:
        A :class:`StreamingPatternResult` whose ``text_stream`` yields deltas
        and whose ``cost`` becomes accurate once the stream is drained.

    Raises:
        BudgetExhaustedError: If the budget is exhausted before dispatch.
    """
    if retry is not None:
        logging.getLogger(__name__).warning(
            "retry is not supported for streaming and will be ignored "
            "(a partial stream cannot be replayed)."
        )

    # ---- no-await critical section: check then reserve ----
    # No ``await`` must be inserted between _check_budget and reserve_call();
    # see checked_complete() and executionkit/cost.py for the concurrency
    # contract this upholds.
    if budget is not None:
        _check_budget(
            budget,
            tracker.to_usage(),
            tuple(_BUDGET_FIELD_LABELS),
            sentinel_suffix="(forwarded from pipe)",
            exceeded_suffix="before dispatch",
        )
    tracker.reserve_call()
    # ---- end critical section ----
    await emit_trace(
        trace,
        TraceEvent.create("llm_call_start", {"cost": tracker.to_usage()}),
    )

    usage_sink: list[LLMResponse] = []
    raw_stream = provider.stream(messages, usage_sink=usage_sink, **kwargs)

    async def _tracked_stream() -> AsyncIterator[str]:
        try:
            async for delta in raw_stream:
                yield delta
        except Exception as exc:
            await emit_trace(
                trace,
                TraceEvent.create(
                    "llm_call_error",
                    {"error_type": type(exc).__name__, "cost": tracker.to_usage()},
                ),
            )
            raise
        response = usage_sink[-1] if usage_sink else LLMResponse(content="")
        tracker.record_without_call(response)
        await emit_trace(
            trace,
            TraceEvent.create(
                "llm_call_end",
                {
                    "cost": tracker.to_usage(),
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    # Redact before emitting: a streamed completion can carry a
                    # credential echoed from the prompt or upstream payload.
                    "content": _redact_sensitive(response.content),
                },
            ),
        )

    return StreamingPatternResult(
        text_stream=_tracked_stream(),
        metadata=MappingProxyType({"streaming": True}),
        _usage_source=tracker.to_usage,
    )


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
        here. reserve_call() and record_without_call() are the accounting API
        used by checked_complete().
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
