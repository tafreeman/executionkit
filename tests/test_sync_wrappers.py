from __future__ import annotations

import asyncio

import pytest

import executionkit
from executionkit._mock import MockProvider


def test_consensus_sync_returns_pattern_result() -> None:
    provider = MockProvider(responses=["answer", "answer", "answer"])
    result = executionkit.consensus_sync(provider, "What is 1+1?", num_samples=3)
    assert result.value == "answer"
    assert result.cost.llm_calls >= 0


def test_refine_loop_sync_returns_pattern_result() -> None:
    # Call order: 1) initial answer, 2) evaluator score (must be numeric).
    # Score "10" → 1.0 → converged immediately, no refinement round needed.
    responses = ["my answer", "10"]
    provider = MockProvider(responses=responses)
    result = executionkit.refine_loop_sync(provider, "Explain gravity")
    assert isinstance(result.value, str)
    assert result.cost.llm_calls >= 0


def test_react_loop_sync_returns_pattern_result() -> None:
    provider = MockProvider(responses=["Final answer: 42"])
    result = executionkit.react_loop_sync(provider, "What is 6 * 7?", tools=[])
    assert isinstance(result.value, str)


def test_structured_sync_returns_pattern_result() -> None:
    provider = MockProvider(responses=['{"answer": 42}'])
    result = executionkit.structured_sync(provider, "Return JSON")
    assert result.value == {"answer": 42}


def test_sync_wrapper_raises_in_active_event_loop() -> None:
    provider = MockProvider(responses=["hi"] * 10)

    async def inner() -> None:
        executionkit.consensus_sync(provider, "test")

    with pytest.raises(RuntimeError, match="async context"):
        asyncio.run(inner())
