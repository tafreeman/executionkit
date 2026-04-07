"""Tests for compose.py — pipe() function."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.compose import _subtract, pipe
from executionkit.provider import BudgetExhaustedError, LLMResponse
from executionkit.types import PatternResult, TokenUsage

# ---------------------------------------------------------------------------
# Helpers — lightweight mock pattern functions
# ---------------------------------------------------------------------------


def _make_response(
    content: str, input_tokens: int = 10, output_tokens: int = 5
) -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=MappingProxyType({
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
        }),
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


@pytest.mark.asyncio
async def test_pipe_no_steps_returns_prompt_as_is() -> None:
    provider = MockProvider(responses=["irrelevant"])
    result = await pipe(provider, "hello world")
    assert result.value == "hello world"
    assert result.cost == TokenUsage()


@pytest.mark.asyncio
async def test_pipe_single_step() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hello", _upper_step)
    assert result.value == "HELLO"
    assert result.cost.llm_calls == 1


@pytest.mark.asyncio
async def test_pipe_chains_two_steps() -> None:
    provider = MockProvider(responses=[])
    # echo passes "hello" -> upper makes it "HELLO"
    result = await pipe(provider, "hello", _echo_step, _upper_step)
    assert result.value == "HELLO"
    assert result.cost.llm_calls == 2


@pytest.mark.asyncio
async def test_pipe_accumulates_costs_across_steps() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hello", _echo_step, _upper_step)
    # _echo_step: 10 in, 5 out, 1 call
    # _upper_step: 8 in, 4 out, 1 call
    assert result.cost.input_tokens == 18
    assert result.cost.output_tokens == 9
    assert result.cost.llm_calls == 2


@pytest.mark.asyncio
async def test_pipe_three_steps_accumulates_all_costs() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hi", _echo_step, _upper_step, _echo_step)
    # echo(10+5+1) + upper(8+4+1) + echo(10+5+1)
    assert result.cost.input_tokens == 10 + 8 + 10
    assert result.cost.output_tokens == 5 + 4 + 5
    assert result.cost.llm_calls == 3


@pytest.mark.asyncio
async def test_pipe_value_threads_through_steps() -> None:
    provider = MockProvider(responses=[])
    # echo passes prompt unchanged, then append adds "!"
    result = await pipe(provider, "hello", _echo_step, _append_step)
    assert result.value == "hello!"


@pytest.mark.asyncio
async def test_pipe_shared_kwargs_forwarded() -> None:
    provider = MockProvider(responses=[])
    result = await pipe(provider, "hi", _append_step, suffix="?")
    assert result.value == "hi?"


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_pipe_without_max_budget_passes_no_max_cost() -> None:
    _budget_received.clear()
    provider = MockProvider(responses=[])

    await pipe(provider, "x", _capture_budget_step)

    assert len(_budget_received) == 1
    assert _budget_received[0] is None


@pytest.mark.asyncio
async def test_pipe_budget_exhausted_uses_sentinel() -> None:
    """Exhausted budget fields are forwarded as -1, not 0, to avoid 'unlimited' misread."""
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
