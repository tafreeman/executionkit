"""Composition utilities for chaining reasoning patterns.

:func:`pipe` threads the output of one pattern as the prompt to the next,
accumulating costs and optionally sharing a token budget across all steps.
"""

from __future__ import annotations

import copy
import inspect
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from executionkit.provider import ExecutionKitError, LLMProvider

if TYPE_CHECKING:
    from collections.abc import Awaitable
from executionkit.types import PatternResult, TokenUsage


class PatternStep(Protocol):
    """Callable protocol for a single step in a :func:`pipe` chain.

    Each step must accept ``(provider, prompt, **kwargs)`` and return an
    awaitable :class:`~executionkit.types.PatternResult`.  Extra keyword
    arguments (e.g. ``max_cost``) are filtered to only those the step
    actually accepts, so steps that do not declare ``**kwargs`` will not
    receive unsupported arguments.
    """

    def __call__(
        self,
        provider: LLMProvider,
        prompt: str,
        **kwargs: Any,
    ) -> Awaitable[PatternResult[Any]]: ...


def _subtract(total: TokenUsage, used: TokenUsage) -> TokenUsage:
    """Return remaining budget after subtracting *used* from *total*.

    Convention:
    - ``0`` on a field means "no limit" — preserved as-is.
    - ``> 0`` means tokens/calls still available.
    - ``-1`` means the field was limited and is now fully exhausted.

    Using ``-1`` (rather than clamping to ``0``) prevents
    :func:`~executionkit.patterns.base.checked_complete` from
    misreading an exhausted budget as "unlimited".
    """

    def _remaining(budget: int, spent: int) -> int:
        if budget == 0:  # unlimited field — preserve it
            return 0
        remaining = budget - spent
        return remaining if remaining > 0 else -1  # -1 means exhausted

    return TokenUsage(
        input_tokens=_remaining(total.input_tokens, used.input_tokens),
        output_tokens=_remaining(total.output_tokens, used.output_tokens),
        llm_calls=_remaining(total.llm_calls, used.llm_calls),
    )


def _filter_kwargs(step: PatternStep, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Filter ``kwargs`` to only keys accepted by ``step``'s signature.

    If the step declares ``**kwargs``, all keys are passed through unchanged.
    Otherwise only parameters explicitly listed in the signature are kept,
    preventing ``TypeError`` when chaining patterns with different keyword sets.
    """
    try:
        sig = inspect.signature(step)
    except (ValueError, TypeError):
        return kwargs  # uninspectable callable — pass everything

    params = sig.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs

    allowed = {
        name
        for name, p in params.items()
        if name not in {"provider", "prompt"}
        and p.kind
        in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    return {k: v for k, v in kwargs.items() if k in allowed}


async def pipe(
    provider: LLMProvider,
    prompt: str,
    *steps: PatternStep,
    max_budget: TokenUsage | None = None,
    **shared_kwargs: Any,
) -> PatternResult[Any]:
    """Chain reasoning patterns, threading output as the next prompt.

    Each *step* must be an async callable with the signature::

        async def step(provider, prompt, **kwargs) -> PatternResult[Any]

    The ``value`` of each result is converted to a string and passed as the
    *prompt* to the following step.  Costs are accumulated and, when
    *max_budget* is given, the remaining budget is forwarded to each step
    via the ``max_cost`` keyword argument.

    Args:
        provider: LLM provider passed unchanged to every step.
        prompt: Initial input prompt.
        *steps: Async pattern callables to chain in order.
        max_budget: Optional shared token/call budget across all steps.
        **shared_kwargs: Extra keyword arguments forwarded to every step.

    Returns:
        The :class:`~executionkit.types.PatternResult` from the final step,
        with its ``cost`` replaced by the cumulative cost across all steps.
        If *steps* is empty the prompt is returned as-is with zero cost.

        The result ``metadata`` gains ``step_costs``: a ``tuple`` of per-step
        :class:`~executionkit.types.TokenUsage` deltas in execution order. On the
        error path the same ``step_costs`` (including the failing step's partial
        spend) is attached to the re-raised exception's ``metadata``.
    """
    if not steps:
        return PatternResult(value=prompt)

    total_cost = TokenUsage()
    current_prompt: str = prompt
    last_result: PatternResult[Any] | None = None
    step_metadata: list[dict[str, Any]] = []
    step_costs: list[TokenUsage] = []

    for step in steps:
        step_kwargs = dict(shared_kwargs)
        if max_budget is not None:
            step_kwargs["max_cost"] = _subtract(max_budget, total_cost)
        filtered_kwargs = _filter_kwargs(step, step_kwargs)

        try:
            result: PatternResult[Any] = await step(
                provider, current_prompt, **filtered_kwargs
            )
        except ExecutionKitError as exc:
            # Record the failing step's partial spend, then raise a shallow copy
            # carrying the accumulated cost.  The original exception is NOT
            # mutated (immutability): a fresh metadata dict is assigned, and the
            # cause chain and traceback are preserved.
            step_costs.append(exc.cost)
            new_exc = copy.copy(exc)
            new_exc.cost = total_cost + exc.cost
            new_exc.metadata = {**exc.metadata, "step_costs": tuple(step_costs)}
            raise new_exc.with_traceback(exc.__traceback__) from exc.__cause__

        step_costs.append(result.cost)
        total_cost = total_cost + result.cost
        current_prompt = str(result.value)
        step_metadata.append(dict(result.metadata))
        last_result = result

    assert last_result is not None  # noqa: S101  # guarded by early return above
    final_metadata: dict[str, Any] = dict(last_result.metadata)
    final_metadata["step_count"] = len(steps)
    final_metadata["step_metadata"] = step_metadata
    final_metadata["step_costs"] = tuple(step_costs)
    return PatternResult(
        value=last_result.value,
        score=last_result.score,
        cost=total_cost,
        metadata=MappingProxyType(final_metadata),
    )
