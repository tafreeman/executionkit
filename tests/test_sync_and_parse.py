"""Tests for sync wrappers (_run_sync, consensus_sync, etc.) and _parse_score."""

from __future__ import annotations

import asyncio
from types import MappingProxyType
from typing import Any

import pytest

from executionkit import (
    consensus_sync,
    pipe_sync,
    react_loop_sync,
    refine_loop_sync,
)
from executionkit.__init__ import _run_sync
from executionkit._mock import MockProvider
from executionkit.patterns.refine_loop import _parse_score
from executionkit.types import PatternResult, TokenUsage, Tool

# ---------------------------------------------------------------------------
# _parse_score
# ---------------------------------------------------------------------------


class TestParseScore:
    def test_plain_integer(self) -> None:
        assert _parse_score("8") == 8.0

    def test_plain_float(self) -> None:
        assert _parse_score("7.5") == 7.5

    def test_whitespace_stripped(self) -> None:
        assert _parse_score("  9  ") == 9.0

    def test_number_with_surrounding_text(self) -> None:
        # Falls back to regex extraction
        assert _parse_score("I'd rate this 8.5 out of 10") == 8.5

    def test_number_at_start_of_text(self) -> None:
        assert _parse_score("7 — good quality") == 7.0

    def test_zero_score(self) -> None:
        assert _parse_score("0") == 0.0

    def test_ten_score(self) -> None:
        assert _parse_score("10") == 10.0

    def test_no_number_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse score"):
            _parse_score("excellent quality")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse score"):
            _parse_score("")

    def test_only_whitespace_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse score"):
            _parse_score("   ")

    def test_decimal_only(self) -> None:
        assert _parse_score("0.75") == 0.75

    def test_number_in_markdown_response(self) -> None:
        assert _parse_score("**Score:** 9 out of 10") == 9.0


# ---------------------------------------------------------------------------
# _run_sync
# ---------------------------------------------------------------------------


class TestRunSync:
    def test_runs_coroutine_synchronously(self) -> None:
        async def simple_coro() -> str:
            return "result"

        result = _run_sync(simple_coro())
        assert result == "result"

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_raises_in_async_context(self) -> None:
        async def inner() -> None:
            async def coro() -> str:
                return "x"

            with pytest.raises(RuntimeError, match="Cannot use sync wrappers"):
                _run_sync(coro())

        asyncio.run(inner())


# ---------------------------------------------------------------------------
# consensus_sync
# ---------------------------------------------------------------------------


class TestConsensusSyncWrapper:
    def test_consensus_sync_returns_result(self) -> None:
        provider = MockProvider(responses=["answer"] * 3)
        result = consensus_sync(provider, "question", num_samples=3)
        assert isinstance(result, PatternResult)
        assert result.value == "answer"
        assert result.cost.llm_calls == 3

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_consensus_sync_raises_in_async_context(self) -> None:
        async def inner() -> None:
            provider = MockProvider(responses=["a"])
            with pytest.raises(RuntimeError, match="Cannot use sync wrappers"):
                consensus_sync(provider, "q", num_samples=1)

        asyncio.run(inner())


# ---------------------------------------------------------------------------
# refine_loop_sync
# ---------------------------------------------------------------------------


class TestRefineLoopSyncWrapper:
    def test_refine_loop_sync_returns_result(self) -> None:
        async def fast_eval(response: str, provider: Any) -> float:
            return 0.95

        provider = MockProvider(responses=["good answer"])
        result = refine_loop_sync(
            provider,
            "prompt",
            evaluator=fast_eval,
            target_score=0.9,
        )
        assert isinstance(result, PatternResult)
        assert isinstance(result.value, str)


# ---------------------------------------------------------------------------
# react_loop_sync
# ---------------------------------------------------------------------------


class TestReactLoopSyncWrapper:
    def test_react_loop_sync_returns_result(self) -> None:
        from executionkit.provider import LLMResponse

        final = LLMResponse(
            content="Direct answer",
            tool_calls=(),
            finish_reason="stop",
            usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
        )
        provider = MockProvider(responses=[final])

        async def noop(query: str) -> str:
            return "result"

        tool = Tool(
            name="search",
            description="Search",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
            execute=noop,
        )

        result = react_loop_sync(provider, "question", [tool])
        assert isinstance(result, PatternResult)
        assert result.value == "Direct answer"


# ---------------------------------------------------------------------------
# pipe_sync
# ---------------------------------------------------------------------------


class TestPipeSyncWrapper:
    def test_pipe_sync_no_steps(self) -> None:
        provider = MockProvider(responses=[])
        result = pipe_sync(provider, "hello")
        assert result.value == "hello"
        assert result.cost == TokenUsage()

    def test_pipe_sync_with_step(self) -> None:
        async def _upper(
            provider: Any, prompt: str, **kwargs: Any
        ) -> PatternResult[str]:
            return PatternResult(
                value=prompt.upper(),
                cost=TokenUsage(input_tokens=5, output_tokens=3, llm_calls=1),
            )

        provider = MockProvider(responses=[])
        result = pipe_sync(provider, "hello", _upper)
        assert result.value == "HELLO"
