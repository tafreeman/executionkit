"""Tests for the map_reduce() pattern.

All tests use MockProvider exclusively — no real API calls are made.
Covers: fan-out mapping, reduce phase, empty input, budget accounting,
template validation, concurrency bounding, and cost accumulation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from executionkit._mock import MockProvider
from executionkit.engine.retry import RetryConfig
from executionkit.patterns.map_reduce import map_reduce
from executionkit.provider import BudgetExhaustedError, LLMResponse, ProviderError
from executionkit.types import TokenUsage

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

# Reusable prompt templates for most tests.
_MAP_TEMPLATE = "Summarize this: {item}"
_REDUCE_TEMPLATE = "Combine these summaries: {mapped_outputs}"


class TestMapReduceHappyPath:
    async def test_maps_over_n_inputs_and_reduces(self) -> None:
        """Map 3 inputs to 3 responses, then reduce to a single output."""
        # 3 map responses + 1 reduce response = 4 total
        provider = MockProvider(
            responses=["summary_a", "summary_b", "summary_c", "final"]
        )
        result = await map_reduce(
            provider,
            inputs=["a", "b", "c"],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
        )
        assert result.value == "final"
        assert result.metadata["map_count"] == 3
        assert result.metadata["reduce_calls"] == 1
        assert result.metadata["total_calls"] == 4

    async def test_map_prompts_contain_items(self) -> None:
        """Each map call receives the rendered template for its item."""
        provider = MockProvider(responses=["r1", "r2", "combined"])
        await map_reduce(
            provider,
            inputs=["apple", "banana"],
            map_prompt_template="Describe: {item}",
            reduce_prompt_template="Join: {mapped_outputs}",
        )
        assert len(provider.calls) == 3
        map_call_0_content = provider.calls[0].messages[0]["content"]
        map_call_1_content = provider.calls[1].messages[0]["content"]
        assert "apple" in map_call_0_content
        assert "banana" in map_call_1_content

    async def test_reduce_prompt_contains_mapped_outputs(self) -> None:
        """The reduce call receives the joined map outputs in its prompt."""
        provider = MockProvider(responses=["sum1", "sum2", "final_answer"])
        await map_reduce(
            provider,
            inputs=["x", "y"],
            map_prompt_template="Summarize: {item}",
            reduce_prompt_template="Reduce: {mapped_outputs}",
        )
        reduce_call_content = provider.calls[2].messages[0]["content"]
        assert "sum1" in reduce_call_content
        assert "sum2" in reduce_call_content

    async def test_single_input(self) -> None:
        """Single input: 1 map call + 1 reduce call = 2 total."""
        provider = MockProvider(responses=["mapped", "reduced"])
        result = await map_reduce(
            provider,
            inputs=["only"],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
        )
        assert result.value == "reduced"
        assert result.metadata["map_count"] == 1
        assert result.metadata["total_calls"] == 2

    async def test_result_is_pattern_result_with_correct_shape(self) -> None:
        """Result has value, score=None, cost, and metadata."""
        provider = MockProvider(responses=["m", "r"])
        result = await map_reduce(
            provider,
            inputs=["item"],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
        )
        assert result.score is None
        assert result.cost.llm_calls == 2
        assert isinstance(result.metadata["map_count"], int)


class TestMapReduceEmptyInput:
    async def test_empty_inputs_skips_map_phase(self) -> None:
        """No inputs: map phase is skipped, only one reduce call is made."""
        provider = MockProvider(responses=["empty_reduce"])
        result = await map_reduce(
            provider,
            inputs=[],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
        )
        assert result.value == "empty_reduce"
        assert result.metadata["map_count"] == 0
        assert result.metadata["reduce_calls"] == 1
        assert result.metadata["total_calls"] == 1
        # Only the reduce call was made.
        assert provider.call_count == 1

    async def test_empty_inputs_reduce_prompt_has_empty_placeholder(self) -> None:
        """With no inputs, {mapped_outputs} is replaced by an empty string."""
        provider = MockProvider(responses=["result"])
        await map_reduce(
            provider,
            inputs=[],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template="Summary: {mapped_outputs}",
        )
        reduce_content = provider.calls[0].messages[0]["content"]
        # {mapped_outputs} replaced by "" — text before placeholder remains
        assert "Summary: " in reduce_content


class TestMapReduceBudgetAccounting:
    async def test_cost_accumulates_across_map_and_reduce(self) -> None:
        """Total cost tracks all map + reduce calls via CostTracker."""
        from types import MappingProxyType

        from executionkit.provider import LLMResponse

        # Use explicit LLMResponse objects so token counts are non-zero.
        def _resp(content: str) -> LLMResponse:
            return LLMResponse(
                content=content,
                finish_reason="stop",
                usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
            )

        provider = MockProvider(responses=[_resp("a"), _resp("b"), _resp("combined")])
        result = await map_reduce(
            provider,
            inputs=["x", "y"],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
        )
        # 2 map + 1 reduce = 3 calls total
        assert result.cost.llm_calls == 3
        # 3 calls x 10 input tokens each
        assert result.cost.input_tokens == 30
        assert result.cost.output_tokens == 15

    async def test_budget_exhausted_on_reduce(self) -> None:
        """BudgetExhaustedError raised when budget is exhausted at the reduce step.

        Set budget to exactly the number of map calls so the reduce call is
        rejected.  This exercises the budget path without relying on
        concurrent failure semantics from gather_strict.
        """
        n_inputs = 2
        provider = MockProvider(responses=["r"] * 10)
        # Budget exactly covers the map calls but not the reduce call.
        tight_budget = TokenUsage(llm_calls=n_inputs)
        with pytest.raises(BudgetExhaustedError):
            await map_reduce(
                provider,
                inputs=["a", "b"],
                map_prompt_template=_MAP_TEMPLATE,
                reduce_prompt_template=_REDUCE_TEMPLATE,
                max_cost=tight_budget,
            )


class TestMapReduceValidation:
    async def test_max_concurrency_zero_raises(self) -> None:
        provider = MockProvider(responses=["x"])
        with pytest.raises(ValueError, match="max_concurrency must be >= 1"):
            await map_reduce(
                provider,
                inputs=["a"],
                map_prompt_template=_MAP_TEMPLATE,
                reduce_prompt_template=_REDUCE_TEMPLATE,
                max_concurrency=0,
            )

    async def test_max_tokens_zero_raises(self) -> None:
        provider = MockProvider(responses=["x"])
        with pytest.raises(ValueError, match="max_tokens must be >= 1"):
            await map_reduce(
                provider,
                inputs=["a"],
                map_prompt_template=_MAP_TEMPLATE,
                reduce_prompt_template=_REDUCE_TEMPLATE,
                max_tokens=0,
            )

    async def test_map_template_missing_placeholder_raises(self) -> None:
        provider = MockProvider(responses=["x"])
        with pytest.raises(ValueError, match=r"\{item\}"):
            await map_reduce(
                provider,
                inputs=["a"],
                map_prompt_template="No placeholder here",
                reduce_prompt_template=_REDUCE_TEMPLATE,
            )

    async def test_reduce_template_missing_placeholder_raises(self) -> None:
        provider = MockProvider(responses=["x", "y"])
        with pytest.raises(ValueError, match=r"\{mapped_outputs\}"):
            await map_reduce(
                provider,
                inputs=["a"],
                map_prompt_template=_MAP_TEMPLATE,
                reduce_prompt_template="No placeholder here",
            )


class TestMapReduceConcurrency:
    async def test_bounded_concurrency_does_not_exceed_limit(self) -> None:
        """All N map calls are made and N+1 total calls recorded."""
        n_inputs = 5
        provider = MockProvider(responses=["r"] * (n_inputs + 1))
        result = await map_reduce(
            provider,
            inputs=[f"item_{i}" for i in range(n_inputs)],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
            max_concurrency=2,
        )
        assert provider.call_count == n_inputs + 1
        assert result.metadata["total_calls"] == n_inputs + 1


class TestMapReducePartialFailure:
    async def test_single_map_failure_propagates(self) -> None:
        """When one MAP call fails, the exception propagates out of map_reduce.

        gather_strict uses asyncio.TaskGroup with all-or-nothing semantics:
        a single task failure is unwrapped from the ExceptionGroup and
        re-raised directly.  Retries are disabled (max_retries=0) so the
        first failure surfaces immediately rather than being retried away —
        ProviderError is retryable under the default RetryConfig.
        """

        class _FailOnItemBProvider:
            """Satisfies LLMProvider; fails deterministically for ``item_b``."""

            supports_tools = True

            async def complete(
                self,
                messages: Sequence[dict[str, Any]],
                *,
                temperature: float | None = None,
                max_tokens: int | None = None,
                tools: Sequence[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> LLMResponse:
                content = str(messages[0].get("content", ""))
                if "item_b" in content:
                    raise ProviderError("simulated provider failure")
                return LLMResponse(content="ok")

        provider = _FailOnItemBProvider()
        with pytest.raises(ProviderError, match="simulated provider failure"):
            await map_reduce(
                provider,  # type: ignore[arg-type]
                inputs=["item_a", "item_b", "item_c"],
                map_prompt_template=_MAP_TEMPLATE,
                reduce_prompt_template=_REDUCE_TEMPLATE,
                retry=RetryConfig(max_retries=0),
            )


class TestMapReduceRetryAccounting:
    """Finding EK#3: total_calls counts every dispatched wire attempt,
    including failed retries, so it can exceed map_count + 1."""

    async def test_total_calls_exceeds_map_count_plus_one_when_retried(self) -> None:
        """A retried map call adds an extra dispatched wire attempt."""

        class _FailFirstCallProvider:
            """Fails (retryably) on the very first call; always succeeds after."""

            supports_tools = True

            def __init__(self) -> None:
                self._call_count = 0

            async def complete(
                self,
                messages: Sequence[dict[str, Any]],
                *,
                temperature: float | None = None,
                max_tokens: int | None = None,
                tools: Sequence[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> LLMResponse:
                self._call_count += 1
                if self._call_count == 1:
                    raise ProviderError("simulated transient failure")
                return LLMResponse(content="ok")

        provider = _FailFirstCallProvider()
        result = await map_reduce(
            provider,  # type: ignore[arg-type]
            inputs=["only"],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
            retry=RetryConfig(max_retries=2, base_delay=0.0),
        )

        assert result.metadata["total_calls"] > result.metadata["map_count"] + 1


class TestMapReduceSync:
    def test_map_reduce_sync_returns_same_shape_as_async(self) -> None:
        """map_reduce_sync (called from non-async context) returns a
        PatternResult with the same shape as the async version."""
        from executionkit import map_reduce_sync

        provider = MockProvider(responses=["sum_a", "sum_b", "combined"])
        result = map_reduce_sync(
            provider,
            ["alpha", "beta"],
            map_prompt_template=_MAP_TEMPLATE,
            reduce_prompt_template=_REDUCE_TEMPLATE,
        )
        assert result.value == "combined"
        assert result.score is None
        assert result.metadata["map_count"] == 2
        assert result.metadata["reduce_calls"] == 1
        assert result.metadata["total_calls"] == 3
        assert result.cost.llm_calls == 3
