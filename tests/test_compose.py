"""Tests for compose.py — pipe() function."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.compose import _filter_kwargs, _subtract, pipe
from executionkit.cost import CostTracker
from executionkit.errors import BudgetExhaustedError
from executionkit.provider import LLMResponse
from executionkit.types import PatternResult, TokenUsage

# ---------------------------------------------------------------------------
# Helpers — lightweight mock pattern functions
# ---------------------------------------------------------------------------


def _make_response(
    content: str, input_tokens: int = 10, output_tokens: int = 5
) -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=MappingProxyType(
            {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
            }
        ),
    )


async def _echo_step(
    provider: Any,
    prompt: str,
    *,
    max_cost: TokenUsage | None = None,
    **kwargs: Any,
) -> PatternResult[str]:
    """Step that echoes the prompt as-is with a small fixed cost."""
    cost = TokenUsage(input_tokens=10, output_tokens=5, llm_calls=1)
    return PatternResult(value=prompt, cost=cost)


async def _upper_step(
    provider: Any,
    prompt: str,
    *,
    max_cost: TokenUsage | None = None,
    **kwargs: Any,
) -> PatternResult[str]:
    """Step that uppercases the prompt."""
    cost = TokenUsage(input_tokens=8, output_tokens=4, llm_calls=1)
    return PatternResult(value=prompt.upper(), cost=cost)


async def _append_step(
    provider: Any,
    prompt: str,
    *,
    suffix: str = "!",
    max_cost: TokenUsage | None = None,
    **kwargs: Any,
) -> PatternResult[str]:
    """Step that appends a suffix to the prompt."""
    cost = TokenUsage(input_tokens=6, output_tokens=3, llm_calls=1)
    return PatternResult(value=prompt + suffix, cost=cost)


_budget_received: list[TokenUsage | None] = []


async def _capture_budget_step(
    provider: Any,
    prompt: str,
    *,
    max_cost: TokenUsage | None = None,
    **kwargs: Any,
) -> PatternResult[str]:
    """Step that records the budget it received for inspection."""
    _budget_received.append(max_cost)
    cost = TokenUsage(input_tokens=5, output_tokens=2, llm_calls=1)
    return PatternResult(value=prompt, cost=cost)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_pipe_no_steps_returns_prompt_as_is() -> None:
    provider = MockProvider(responses=["irrelevant"])
    result = await pipe(provider, "hello world")
    assert result.value == "hello world"
    assert result.cost == TokenUsage()


async def test_pipe_single_step() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hello", _upper_step)
    assert result.value == "HELLO"
    assert result.cost.llm_calls == 1


async def test_pipe_chains_two_steps() -> None:
    provider = MockProvider(responses=[])
    # echo passes "hello" -> upper makes it "HELLO"
    result = await pipe(provider, "hello", _echo_step, _upper_step)
    assert result.value == "HELLO"
    assert result.cost.llm_calls == 2


async def test_pipe_accumulates_costs_across_steps() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hello", _echo_step, _upper_step)
    # _echo_step: 10 in, 5 out, 1 call
    # _upper_step: 8 in, 4 out, 1 call
    assert result.cost.input_tokens == 18
    assert result.cost.output_tokens == 9
    assert result.cost.llm_calls == 2


async def test_pipe_three_steps_accumulates_all_costs() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hi", _echo_step, _upper_step, _echo_step)
    # echo(10+5+1) + upper(8+4+1) + echo(10+5+1)
    assert result.cost.input_tokens == 10 + 8 + 10
    assert result.cost.output_tokens == 5 + 4 + 5
    assert result.cost.llm_calls == 3


async def test_pipe_value_threads_through_steps() -> None:
    provider = MockProvider(responses=[])
    # echo passes prompt unchanged, then append adds "!"
    result = await pipe(provider, "hello", _echo_step, _append_step)
    assert result.value == "hello!"


async def test_pipe_shared_kwargs_forwarded() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hi", _append_step, suffix="?")
    assert result.value == "hi?"


async def test_pipe_with_max_budget_passes_remaining_to_steps() -> None:
    _budget_received.clear()
    provider = MockProvider(responses=[])
    budget = TokenUsage(input_tokens=100, output_tokens=50, llm_calls=10)

    await pipe(
        provider, "x", _capture_budget_step, _capture_budget_step, max_budget=budget
    )

    assert len(_budget_received) == 2
    first_budget = _budget_received[0]
    second_budget = _budget_received[1]

    # First step gets the full budget
    assert first_budget == budget

    # Second step gets budget minus what the first step used
    # _capture_budget_step costs: 5 in, 2 out, 1 call
    assert second_budget is not None
    assert second_budget.input_tokens == 100 - 5
    assert second_budget.output_tokens == 50 - 2
    assert second_budget.llm_calls == 10 - 1


async def test_pipe_without_max_budget_passes_no_max_cost() -> None:
    _budget_received.clear()
    provider = MockProvider(responses=[])

    await pipe(provider, "x", _capture_budget_step)

    assert len(_budget_received) == 1
    assert _budget_received[0] is None


async def test_pipe_budget_exhausted_uses_sentinel() -> None:
    """Forward exhausted budget fields as -1 (not 0) to avoid 'unlimited' misread."""
    _budget_received.clear()
    provider = MockProvider(responses=[])
    # Very tight budget — first step will consume more than it
    tiny_budget = TokenUsage(input_tokens=3, output_tokens=1, llm_calls=1)

    await pipe(
        provider,
        "x",
        _capture_budget_step,
        _capture_budget_step,
        max_budget=tiny_budget,
    )

    second_budget = _budget_received[1]
    assert second_budget is not None
    assert second_budget.input_tokens == -1
    assert second_budget.output_tokens == -1
    assert second_budget.llm_calls == -1


async def test_pipe_returns_last_step_metadata() -> None:
    async def _meta_step(
        provider: Any, prompt: str, *, max_cost: TokenUsage | None = None, **kwargs: Any
    ) -> PatternResult[str]:
        return PatternResult(
            value="done", cost=TokenUsage(), metadata=MappingProxyType({"key": "value"})
        )

    provider = MockProvider(responses=[])
    result = await pipe(provider, "input", _meta_step)
    assert result.metadata["key"] == "value"
    assert result.metadata["step_count"] == 1


async def test_pipe_returns_last_step_score() -> None:
    async def _scored_step(
        provider: Any, prompt: str, *, max_cost: TokenUsage | None = None, **kwargs: Any
    ) -> PatternResult[str]:
        return PatternResult(value="result", score=0.95, cost=TokenUsage())

    provider = MockProvider(responses=[])
    result = await pipe(provider, "input", _scored_step)
    assert result.score == pytest.approx(0.95)


def test_pipe_enforces_exhausted_budget() -> None:
    """Budget forwarded from pipe() must not bypass checked_complete when exhausted."""
    # _subtract should use -1 for exhausted fields
    result = _subtract(TokenUsage(llm_calls=2), TokenUsage(llm_calls=2))
    assert result.llm_calls == -1

    result = _subtract(TokenUsage(llm_calls=2), TokenUsage(llm_calls=3))
    assert result.llm_calls == -1  # overspent also exhausted

    # unlimited fields (0) must be preserved
    result = _subtract(TokenUsage(llm_calls=0), TokenUsage(llm_calls=5))
    assert result.llm_calls == 0


# ---------------------------------------------------------------------------
# Error path tests — immutability and cost accumulation
# ---------------------------------------------------------------------------

# Cost charged by each of the helper steps defined above:
#   _echo_step:  input=10, output=5,  calls=1
#   _upper_step: input=8,  output=4,  calls=1


async def _raising_step(
    provider: Any,
    prompt: str,
    *,
    max_cost: TokenUsage | None = None,
    **kwargs: Any,
) -> PatternResult[str]:
    """Step that raises BudgetExhaustedError carrying its own cost."""
    own_cost = TokenUsage(input_tokens=3, output_tokens=2, llm_calls=1)
    raise BudgetExhaustedError("budget gone", cost=own_cost)


async def test_pipe_error_cost_includes_completed_steps() -> None:
    """Exception cost equals prior steps' costs plus the raising step's own cost."""
    provider = MockProvider(responses=[])

    with pytest.raises(BudgetExhaustedError) as exc_info:
        # _echo_step runs successfully (cost: 10 in, 5 out, 1 call)
        # _upper_step runs successfully (cost: 8 in, 4 out, 1 call)
        # _raising_step raises (own cost: 3 in, 2 out, 1 call)
        await pipe(provider, "hello", _echo_step, _upper_step, _raising_step)

    raised = exc_info.value
    expected_input = 10 + 8 + 3
    expected_output = 5 + 4 + 2
    expected_calls = 1 + 1 + 1
    assert raised.cost.input_tokens == expected_input
    assert raised.cost.output_tokens == expected_output
    assert raised.cost.llm_calls == expected_calls


async def test_pipe_error_cost_not_double_counted() -> None:
    """Running the same pipe again must not accumulate cost from a prior run."""
    provider = MockProvider(responses=[])

    with pytest.raises(BudgetExhaustedError) as first:
        await pipe(provider, "hello", _echo_step, _raising_step)

    with pytest.raises(BudgetExhaustedError) as second:
        await pipe(provider, "hello", _echo_step, _raising_step)

    # Both runs are independent; the cost must be the same each time.
    assert first.value.cost == second.value.cost


async def test_pipe_error_original_exception_not_mutated() -> None:
    """The originally-raised exception object must be left unmutated (copy)."""
    original_cost = TokenUsage(input_tokens=3, output_tokens=2, llm_calls=1)

    original_exc: BudgetExhaustedError | None = None

    async def _capturing_raising_step(
        provider: Any,
        prompt: str,
        *,
        max_cost: TokenUsage | None = None,
        **kwargs: Any,
    ) -> PatternResult[str]:
        nonlocal original_exc
        original_exc = BudgetExhaustedError("budget gone", cost=original_cost)
        raise original_exc

    provider = MockProvider(responses=[])

    with pytest.raises(BudgetExhaustedError):
        # _echo_step runs first (cost: 10/5/1 call), then the raising step
        await pipe(provider, "hello", _echo_step, _capturing_raising_step)

    # The original exception object must still carry only its own cost.
    assert original_exc is not None
    assert original_exc.cost == original_cost, (
        "pipe() must not mutate the original exception; "
        f"expected cost={original_cost!r}, got {original_exc.cost!r}"
    )


async def test_pipe_nested_error_cost_accumulated_once() -> None:
    """In a pipe-of-pipes, cost must accumulate exactly once per level."""
    provider = MockProvider(responses=[])

    # Inner pipe: _echo_step (10+5+1) -> _raising_step (3+2+1) raises.
    # Exception exits inner pipe with cost = 10+3=13 in, 5+2=7 out, 2 calls.
    async def inner_pipe(
        provider: Any, prompt: str, **kwargs: Any
    ) -> PatternResult[str]:
        return await pipe(provider, prompt, _echo_step, _raising_step)

    # Outer pipe: _upper_step (8+4+1) runs first, then inner_pipe raises.
    # Exception exits outer pipe with cost = (8 outer) + (13 inner) = 21 in,
    # (4 outer) + (7 inner) = 11 out, (1 outer) + (2 inner) = 3 calls.
    with pytest.raises(BudgetExhaustedError) as exc_info:
        await pipe(provider, "hello", _upper_step, inner_pipe)

    raised = exc_info.value
    # _upper_step: 8 in, 4 out, 1 call (completed in outer pipe)
    # _echo_step:  10 in, 5 out, 1 call (completed in inner pipe)
    # _raising_step: 3 in, 2 out, 1 call (the raising step's own cost)
    assert raised.cost.input_tokens == 8 + 10 + 3
    assert raised.cost.output_tokens == 4 + 5 + 2
    assert raised.cost.llm_calls == 1 + 1 + 1


# ---------------------------------------------------------------------------
# _filter_kwargs — uninspectable callable fallback
# ---------------------------------------------------------------------------


def test_filter_kwargs_uninspectable_callable_passes_all_kwargs() -> None:
    """_filter_kwargs falls back to passing all kwargs for uninspectable callables.

    A callable whose ``__signature__`` property raises ``ValueError`` exercises
    the ``except (ValueError, TypeError)`` branch in ``_filter_kwargs``, which
    must return the original ``kwargs`` dict unchanged.
    """

    class _UninspectableStep:
        """A callable that raises ValueError when inspect.signature() is called."""

        @property
        def __signature__(self) -> None:  # type: ignore[override]
            raise ValueError("no signature available")

        async def __call__(  # pragma: no cover
            self, provider: Any, prompt: str, **kwargs: Any
        ) -> Any: ...

    step = _UninspectableStep()
    kwargs = {"max_cost": TokenUsage(), "extra_key": "value"}
    result = _filter_kwargs(step, kwargs)  # type: ignore[arg-type]
    assert result == kwargs, (
        "_filter_kwargs must return all kwargs unchanged for uninspectable callables"
    )


# ---------------------------------------------------------------------------
# Item B — per-step cost attribution, snapshot(), and TokenUsage.__sub__
# ---------------------------------------------------------------------------


async def test_two_step_pipe_step_costs_has_two_entries() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hello", _echo_step, _upper_step)
    step_costs = result.metadata["step_costs"]
    assert isinstance(step_costs, tuple)
    assert len(step_costs) == 2
    assert step_costs[0] == TokenUsage(input_tokens=10, output_tokens=5, llm_calls=1)
    assert step_costs[1] == TokenUsage(input_tokens=8, output_tokens=4, llm_calls=1)


async def test_step_costs_sum_equals_total_cost() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hello", _echo_step, _upper_step, _append_step)
    summed = TokenUsage()
    for cost in result.metadata["step_costs"]:
        summed = summed + cost
    assert summed == result.cost


async def test_budget_exhausted_step_costs_contains_partial_spend() -> None:
    provider = MockProvider(responses=[])
    with pytest.raises(BudgetExhaustedError) as exc_info:
        await pipe(provider, "hello", _echo_step, _raising_step)
    step_costs = exc_info.value.metadata["step_costs"]
    assert len(step_costs) == 2
    # First entry: the completed echo step. Last: the failing step's partial spend.
    assert step_costs[0] == TokenUsage(input_tokens=10, output_tokens=5, llm_calls=1)
    assert step_costs[-1] == TokenUsage(input_tokens=3, output_tokens=2, llm_calls=1)


async def test_zero_step_pipe_step_costs_is_empty_tuple() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hello")
    # No steps run, so there are no per-step costs to report.
    assert result.metadata.get("step_costs", ()) == ()


def test_snapshot_does_not_mutate_tracker() -> None:
    tracker = CostTracker()
    tracker.add_usage(TokenUsage(input_tokens=5, output_tokens=3, llm_calls=1))
    first = tracker.snapshot()
    second = tracker.snapshot()
    assert first == second == TokenUsage(input_tokens=5, output_tokens=3, llm_calls=1)
    # Taking a snapshot must not advance any counter.
    assert tracker.snapshot() == first


def test_token_usage_sub_returns_field_wise_difference() -> None:
    later = TokenUsage(input_tokens=10, output_tokens=7, llm_calls=3)
    earlier = TokenUsage(input_tokens=4, output_tokens=2, llm_calls=1)
    assert later - earlier == TokenUsage(input_tokens=6, output_tokens=5, llm_calls=2)
