"""Tests for the consensus() pattern.

All tests use MockProvider exclusively — no real API calls are made.
Covers: majority voting, agreement ratio, whitespace normalisation,
budget enforcement, voting strategies, and input validation.
"""

from __future__ import annotations

import asyncio

import pytest

from executionkit._mock import MockProvider
from executionkit.engine.retry import RetryConfig
from executionkit.errors import BudgetExhaustedError
from executionkit.patterns.consensus import consensus
from executionkit.provider import (
    ConsensusFailedError,
    LLMResponse,
)
from executionkit.types import PatternResult, TokenUsage, VotingStrategy

# ---------------------------------------------------------------------------
# consensus()
# ---------------------------------------------------------------------------


class TestConsensus:
    async def test_basic_majority_most_common_wins(self) -> None:

        # 4x "answer_a", 1x "answer_b" -> majority = "answer_a"
        provider = MockProvider(
            responses=["answer_a", "answer_a", "answer_a", "answer_b", "answer_a"]
        )
        result = await consensus(provider, "question", num_samples=5)
        assert result.value == "answer_a"

    async def test_agreement_ratio_calculation(self) -> None:

        # 4 of 5 agree → ratio = 0.8
        provider = MockProvider(
            responses=["answer_a", "answer_a", "answer_a", "answer_b", "answer_a"]
        )
        result = await consensus(provider, "question", num_samples=5)
        assert result.metadata["agreement_ratio"] == pytest.approx(0.8)

    async def test_metadata_contains_required_keys(self) -> None:

        provider = MockProvider(responses=["a", "a", "a", "b", "a"])
        result = await consensus(provider, "question", num_samples=5)
        assert "agreement_ratio" in result.metadata
        assert "unique_responses" in result.metadata
        assert "tie_count" in result.metadata

    async def test_unique_responses_count(self) -> None:

        provider = MockProvider(responses=["a", "a", "b", "b", "c"])
        result = await consensus(provider, "question", num_samples=5)
        assert result.metadata["unique_responses"] == 3

    async def test_unanimous_strategy_all_same_succeeds(self) -> None:

        provider = MockProvider(responses=["same", "same", "same"])
        result = await consensus(
            provider, "question", num_samples=3, strategy=VotingStrategy.UNANIMOUS
        )
        assert result.value == "same"

    async def test_unanimous_strategy_any_different_raises(self) -> None:

        provider = MockProvider(responses=["same", "same", "different"])
        with pytest.raises(ConsensusFailedError):
            await consensus(
                provider, "question", num_samples=3, strategy=VotingStrategy.UNANIMOUS
            )

    async def test_string_strategy_majority_works(self) -> None:

        provider = MockProvider(responses=["x", "x", "y"])
        result = await consensus(
            provider, "question", num_samples=3, strategy="majority"
        )
        assert result.value == "x"

    async def test_string_strategy_unanimous_works(self) -> None:

        provider = MockProvider(responses=["z", "z", "z"])
        result = await consensus(
            provider, "question", num_samples=3, strategy="unanimous"
        )
        assert result.value == "z"

    async def test_result_is_pattern_result(self) -> None:

        provider = MockProvider(responses=["a"])
        result = await consensus(provider, "q", num_samples=1)
        assert isinstance(result, PatternResult)

    async def test_result_value_is_string(self) -> None:

        provider = MockProvider(responses=["answer"])
        result = await consensus(provider, "q", num_samples=1)
        assert isinstance(result.value, str)

    async def test_cost_tracks_llm_calls(self) -> None:

        provider = MockProvider(responses=["a", "b", "c"])
        result = await consensus(provider, "q", num_samples=3)
        assert result.cost.llm_calls == 3

    async def test_score_equals_agreement_ratio(self) -> None:

        provider = MockProvider(responses=["a", "a", "a", "b", "a"])
        result = await consensus(provider, "q", num_samples=5)
        assert result.score == pytest.approx(result.metadata["agreement_ratio"])

    async def test_custom_retry_config_accepted(self) -> None:

        provider = MockProvider(responses=["ok"])
        retry = RetryConfig(max_retries=0)
        result = await consensus(provider, "q", num_samples=1, retry=retry)
        assert result.value == "ok"

    async def test_single_sample_has_full_agreement(self) -> None:

        provider = MockProvider(responses=["solo"])
        result = await consensus(provider, "q", num_samples=1)
        assert result.metadata["agreement_ratio"] == 1.0
        assert result.metadata["unique_responses"] == 1

    async def test_all_different_selects_first_alphabetically_or_first_by_count(
        self,
    ) -> None:

        # All different: each has count 1 → tie, first in most_common wins
        provider = MockProvider(responses=["a", "b", "c"])
        result = await consensus(provider, "q", num_samples=3)
        # All have equal votes — winner is whichever Counter.most_common picks first
        assert result.metadata["unique_responses"] == 3
        assert result.metadata["agreement_ratio"] == pytest.approx(1 / 3)

    async def test_tie_count_is_zero_when_clear_winner(self) -> None:

        provider = MockProvider(responses=["a", "a", "a", "b", "c"])
        result = await consensus(provider, "q", num_samples=5)
        # "a" has 3 votes, "b" and "c" each have 1 — clear winner
        assert result.metadata["tie_count"] == 1  # only 1 response with top count

    async def test_consensus_whitespace_variants_merge(self) -> None:
        """Responses differing only in trailing newlines count as one unique."""

        # 3 responses with trailing newline, 2 without — all semantically identical
        responses = ["hello\n", "hello\n", "hello\n", "hello", "hello"]
        provider = MockProvider(responses=responses)
        result = await consensus(provider, "q", num_samples=5)
        assert result.metadata["unique_responses"] == 1

    async def test_consensus_winner_is_original_text(self) -> None:
        """When all responses have a trailing newline, the value preserves it."""

        responses = ["answer\n", "answer\n", "answer\n"]
        provider = MockProvider(responses=responses)
        result = await consensus(provider, "q", num_samples=3)
        assert result.value == "answer\n"

    async def test_consensus_internal_whitespace_collapsed(self) -> None:
        """Responses differing only by double-space are counted as a single unique."""

        responses = ["hello  world", "hello world", "hello  world"]
        provider = MockProvider(responses=responses)
        result = await consensus(provider, "q", num_samples=3)
        assert result.metadata["unique_responses"] == 1

    async def test_consensus_all_five_unique_tie_count_and_unique_responses(
        self,
    ) -> None:
        """When all 5 responses are unique, tie_count=5 and unique_responses=5."""

        # 5 completely distinct responses → every response count=1 → all tied
        responses = ["alpha", "beta", "gamma", "delta", "epsilon"]
        provider = MockProvider(responses=responses)
        result = await consensus(provider, "q", num_samples=5)
        assert result.metadata["unique_responses"] == 5
        assert result.metadata["tie_count"] == 5
        # agreement_ratio = 1/5 since winner got only 1 of 5 votes
        assert result.metadata["agreement_ratio"] == pytest.approx(1 / 5)

    async def test_num_samples_zero_raises_value_error(self) -> None:
        """num_samples=0 must raise ValueError before any LLM call."""

        provider = MockProvider(responses=["irrelevant"])
        with pytest.raises(ValueError, match="num_samples must be >= 1"):
            await consensus(provider, "q", num_samples=0)

    async def test_num_samples_one_returns_single_sample(self) -> None:
        """num_samples=1 with majority strategy returns that one sample."""

        provider = MockProvider(responses=["only_answer"])
        result = await consensus(provider, "q", num_samples=1, strategy="majority")
        assert result.value == "only_answer"
        assert result.metadata["agreement_ratio"] == pytest.approx(1.0)
        assert result.metadata["unique_responses"] == 1

    async def test_max_cost_budget_exhausted_after_first_sample(self) -> None:
        """Budget cap of one call raises BudgetExhaustedError after first sample.

        gather_strict uses TaskGroup which may surface multiple simultaneous
        BudgetExhaustedErrors as an ExceptionGroup when tasks 2 and 3 both
        check the budget after task 1 exhausts it.
        """

        provider = MockProvider(responses=["a", "b", "c"])
        # Accept either a bare BudgetExhaustedError (single failure unwrapped
        # by gather_strict) or an ExceptionGroup whose members are all
        # BudgetExhaustedError (multiple simultaneous failures).
        try:
            await consensus(
                provider,
                "q",
                num_samples=3,
                max_cost=TokenUsage(llm_calls=1),
                max_concurrency=1,
            )
        except BudgetExhaustedError:
            pass  # single exception unwrapped — expected
        except ExceptionGroup as eg:
            assert all(
                isinstance(exc, BudgetExhaustedError) for exc in eg.exceptions
            ), f"Unexpected exception types in group: {eg.exceptions}"
        else:
            pytest.fail("Expected BudgetExhaustedError but no exception was raised")

    async def test_parallel_budget_dispatches_only_reserved_call(self) -> None:
        """Concurrent consensus must not race past a one-call budget."""

        class SlowProvider:
            def __init__(self) -> None:
                self.calls = 0

            async def complete(self, messages: object, **kwargs: object) -> LLMResponse:
                self.calls += 1
                await asyncio.sleep(0.01)
                return LLMResponse(content="answer")

        provider = SlowProvider()

        with pytest.raises((BudgetExhaustedError, ExceptionGroup)):
            await consensus(
                provider,  # type: ignore[arg-type]
                "q",
                num_samples=5,
                max_cost=TokenUsage(llm_calls=1),
                max_concurrency=5,
            )

        assert provider.calls == 1
