"""Tests for kit.py — Kit session class."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from executionkit._mock import MockProvider
from executionkit.kit import Kit
from executionkit.provider import LLMResponse
from executionkit.types import PatternResult, TokenUsage, Tool

if TYPE_CHECKING:
    from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    content: str = "response",
    input_tokens: int = 10,
    output_tokens: int = 5,
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


def _make_result(
    value: str = "result",
    input_tokens: int = 10,
    output_tokens: int = 5,
    llm_calls: int = 1,
) -> PatternResult[str]:
    return PatternResult(
        value=value,
        cost=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            llm_calls=llm_calls,
        ),
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider(responses=["answer"])


@pytest.fixture
def kit(provider: MockProvider) -> Kit:
    return Kit(provider)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_kit_stores_provider(provider: MockProvider) -> None:
    kit = Kit(provider)
    assert kit.provider is provider


def test_kit_initial_usage_is_zero(kit: Kit) -> None:
    assert kit.usage == TokenUsage()


def test_kit_track_cost_false_returns_zero_usage(provider: MockProvider) -> None:
    kit = Kit(provider, track_cost=False)
    assert kit.usage == TokenUsage()


# ---------------------------------------------------------------------------
# consensus delegation
# ---------------------------------------------------------------------------


async def test_kit_consensus_delegates_to_consensus_fn(provider: MockProvider) -> None:
    expected = _make_result(
        "consensus_answer", input_tokens=50, output_tokens=20, llm_calls=5
    )
    with patch(
        "executionkit.kit.consensus", new=AsyncMock(return_value=expected)
    ) as mock_fn:
        kit = Kit(provider)
        result = await kit.consensus("prompt", num_samples=5)

    mock_fn.assert_called_once_with(provider, "prompt", num_samples=5)
    assert result is expected


async def test_kit_consensus_accumulates_cost(provider: MockProvider) -> None:
    result1 = _make_result(input_tokens=20, output_tokens=10, llm_calls=2)
    result2 = _make_result(input_tokens=30, output_tokens=15, llm_calls=3)
    with patch(
        "executionkit.kit.consensus", new=AsyncMock(side_effect=[result1, result2])
    ):
        kit = Kit(provider)
        await kit.consensus("p1")
        await kit.consensus("p2")

    assert kit.usage.input_tokens == 50
    assert kit.usage.output_tokens == 25
    assert kit.usage.llm_calls == 5


async def test_kit_consensus_no_tracking(provider: MockProvider) -> None:
    expected = _make_result(input_tokens=20, output_tokens=10, llm_calls=2)
    with patch("executionkit.kit.consensus", new=AsyncMock(return_value=expected)):
        kit = Kit(provider, track_cost=False)
        await kit.consensus("prompt")

    assert kit.usage == TokenUsage()


# ---------------------------------------------------------------------------
# refine delegation
# ---------------------------------------------------------------------------


async def test_kit_refine_delegates_to_refine_loop(provider: MockProvider) -> None:
    expected = _make_result("refined", input_tokens=40, output_tokens=30, llm_calls=4)
    with patch(
        "executionkit.kit.refine_loop", new=AsyncMock(return_value=expected)
    ) as mock_fn:
        kit = Kit(provider)
        result = await kit.refine("prompt", max_iterations=3)

    mock_fn.assert_called_once_with(provider, "prompt", max_iterations=3)
    assert result is expected


async def test_kit_refine_accumulates_cost(provider: MockProvider) -> None:
    expected = _make_result(input_tokens=15, output_tokens=8, llm_calls=3)
    with patch("executionkit.kit.refine_loop", new=AsyncMock(return_value=expected)):
        kit = Kit(provider)
        await kit.refine("prompt")

    assert kit.usage.input_tokens == 15
    assert kit.usage.output_tokens == 8
    assert kit.usage.llm_calls == 3


# ---------------------------------------------------------------------------
# react delegation
# ---------------------------------------------------------------------------


async def test_kit_react_delegates_to_react_loop(provider: MockProvider) -> None:
    tools: list[Tool] = []
    expected = _make_result(
        "react_answer", input_tokens=60, output_tokens=25, llm_calls=4
    )
    with patch(
        "executionkit.kit.react_loop", new=AsyncMock(return_value=expected)
    ) as mock_fn:
        kit = Kit(provider)
        result = await kit.react("prompt", tools, max_rounds=4)

    mock_fn.assert_called_once_with(provider, "prompt", tools, max_rounds=4)
    assert result is expected


async def test_kit_react_accumulates_cost(provider: MockProvider) -> None:
    expected = _make_result(input_tokens=25, output_tokens=12, llm_calls=3)
    with patch("executionkit.kit.react_loop", new=AsyncMock(return_value=expected)):
        kit = Kit(provider)
        await kit.react("prompt", [])

    assert kit.usage.input_tokens == 25
    assert kit.usage.output_tokens == 12
    assert kit.usage.llm_calls == 3


async def test_kit_react_rejects_non_tool_calling_provider() -> None:
    """react() raises TypeError when the provider is not a ToolCallingProvider."""

    class NoToolsProvider:
        """Satisfies LLMProvider (has complete) but not ToolCallingProvider."""

        async def complete(
            self,
            messages: Sequence[dict[str, Any]],
            *,
            temperature: float | None = None,
            max_tokens: int | None = None,
            tools: Sequence[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> LLMResponse:
            raise NotImplementedError

    kit = Kit(NoToolsProvider())
    with pytest.raises(TypeError, match="ToolCallingProvider"):
        await kit.react("prompt", [])


async def test_kit_react_rejects_provider_with_supports_tools_false() -> None:
    """react() must also reject a provider that has supports_tools=False.

    @runtime_checkable only checks that the attribute *exists*, so a provider
    with supports_tools=False would pass isinstance() — _provider_supports_tools
    closes this gap.  Both kit.py and react_loop.py must use the helper.
    """
    from executionkit.patterns.react_loop import react_loop

    class FalseToolsProvider:
        """Has supports_tools attribute but set to False — structural isinstance
        check passes; value check must catch it."""

        supports_tools: bool = False

        async def complete(
            self,
            messages: Sequence[dict[str, Any]],
            *,
            temperature: float | None = None,
            max_tokens: int | None = None,
            tools: Sequence[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> LLMResponse:
            raise NotImplementedError

    bad_provider = FalseToolsProvider()

    # kit.py path
    kit = Kit(bad_provider)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ToolCallingProvider"):
        await kit.react("prompt", [])

    # react_loop.py path — _validate_react_loop_args called directly
    with pytest.raises(TypeError, match="ToolCallingProvider"):
        await react_loop(bad_provider, "prompt", [])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# pipe delegation
# ---------------------------------------------------------------------------


async def test_kit_pipe_delegates_to_pipe_fn(provider: MockProvider) -> None:
    async def dummy_step(p: Any, prompt: str, **kwargs: Any) -> PatternResult[str]:
        return PatternResult(value=prompt + "_done", cost=TokenUsage())

    expected = _make_result("pipe_done", input_tokens=30, output_tokens=15, llm_calls=2)
    with patch(
        "executionkit.kit.pipe", new=AsyncMock(return_value=expected)
    ) as mock_fn:
        kit = Kit(provider)
        result = await kit.pipe("prompt", dummy_step)

    mock_fn.assert_called_once_with(provider, "prompt", dummy_step)
    assert result is expected


async def test_kit_pipe_accumulates_cost(provider: MockProvider) -> None:
    expected = _make_result(input_tokens=18, output_tokens=9, llm_calls=2)
    with patch("executionkit.kit.pipe", new=AsyncMock(return_value=expected)):
        kit = Kit(provider)
        await kit.pipe("prompt")

    assert kit.usage.input_tokens == 18
    assert kit.usage.output_tokens == 9
    assert kit.usage.llm_calls == 2


# ---------------------------------------------------------------------------
# Cumulative tracking across mixed calls
# ---------------------------------------------------------------------------


async def test_kit_usage_accumulates_across_different_patterns(
    provider: MockProvider,
) -> None:
    r1 = _make_result(input_tokens=10, output_tokens=5, llm_calls=1)
    r2 = _make_result(input_tokens=20, output_tokens=10, llm_calls=2)
    r3 = _make_result(input_tokens=30, output_tokens=15, llm_calls=3)

    with (
        patch("executionkit.kit.consensus", new=AsyncMock(return_value=r1)),
        patch("executionkit.kit.refine_loop", new=AsyncMock(return_value=r2)),
        patch("executionkit.kit.react_loop", new=AsyncMock(return_value=r3)),
    ):
        kit = Kit(provider)
        await kit.consensus("p1")
        await kit.refine("p2")
        await kit.react("p3", [])

    assert kit.usage.input_tokens == 60
    assert kit.usage.output_tokens == 30
    assert kit.usage.llm_calls == 6


# ---------------------------------------------------------------------------
# Cost recording when a pattern raises
# ---------------------------------------------------------------------------


async def test_kit_records_partial_cost_when_pattern_raises(
    provider: MockProvider,
) -> None:
    """A raised ExecutionKit error carries the cost accrued before it aborted;
    Kit.usage must reflect that spend instead of silently dropping it."""
    from executionkit.provider import BudgetExhaustedError

    err = BudgetExhaustedError(
        "over budget",
        cost=TokenUsage(input_tokens=12, output_tokens=4, llm_calls=2),
    )
    with patch("executionkit.kit.consensus", new=AsyncMock(side_effect=err)):
        kit = Kit(provider)
        with pytest.raises(BudgetExhaustedError):
            await kit.consensus("p")

    assert kit.usage.llm_calls == 2
    assert kit.usage.input_tokens == 12
    assert kit.usage.output_tokens == 4


async def test_kit_records_cost_on_failure_end_to_end() -> None:
    """Through the real refine pattern: the budget trips mid-run, and the one
    call dispatched before it is still counted in Kit.usage."""
    from executionkit.provider import BudgetExhaustedError

    async def never_good(value: str, _provider: object) -> float:
        return 0.0

    kit = Kit(MockProvider(responses=["draft", "again"]))
    with pytest.raises(BudgetExhaustedError):
        await kit.refine(
            "improve",
            evaluator=never_good,
            max_cost=TokenUsage(llm_calls=1),
            max_iterations=3,
        )

    # The initial generation reserved one call before the budget tripped.
    assert kit.usage.llm_calls == 1


# ---------------------------------------------------------------------------
# Deterministic smoke tests (use real MockProvider without patching)
# ---------------------------------------------------------------------------


async def test_kit_consensus_smoke_with_mock_provider() -> None:
    """End-to-end: Kit.consensus calls through with MockProvider."""
    # consensus runs 5 samples by default; provide 5 identical answers
    p = MockProvider(responses=["the answer"] * 5)
    kit = Kit(p)
    result = await kit.consensus("What is 2+2?", num_samples=5)

    assert result.value == "the answer"
    assert kit.usage.llm_calls == 5
    assert kit.usage.input_tokens >= 0


async def test_kit_pipe_smoke_no_steps() -> None:
    """pipe with no steps returns prompt unchanged."""
    p = MockProvider(responses=[])
    kit = Kit(p)
    result = await kit.pipe("hello world")

    assert result.value == "hello world"
    assert kit.usage == TokenUsage()
