"""Opt-in live-provider regression tests for every ExecutionKit pattern.

Gate: set EXECUTIONKIT_LIVE_EVAL=1 (plus EXECUTIONKIT_BASE_URL and
EXECUTIONKIT_MODEL) to run.  All tests skip when the env var is absent so the
suite stays green in CI.
"""

from __future__ import annotations

import os

import pytest

from executionkit.evals import live_provider_from_env
from executionkit.patterns.consensus import consensus
from executionkit.patterns.react_loop import react_loop
from executionkit.patterns.refine_loop import refine_loop
from executionkit.patterns.structured import structured
from executionkit.types import Tool

# ---------------------------------------------------------------------------
# structured()
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1",
    reason="set EXECUTIONKIT_LIVE_EVAL=1 to run live endpoint evals",
)
async def test_live_structured_exact_shape() -> None:
    """LIVE-STRUCTURED-01 — structured() returns exact requested shape."""
    provider = live_provider_from_env()
    if provider is None:
        pytest.skip("live eval disabled")

    result = await structured(
        provider,
        'Return only JSON with this exact shape: {"name": "alice", "age": 30}',
        max_retries=1,
        temperature=0.0,
        max_tokens=64,
    )

    assert result.value == {"name": "alice", "age": 30}


@pytest.mark.skipif(
    os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1",
    reason="set EXECUTIONKIT_LIVE_EVAL=1 to run live endpoint evals",
)
async def test_live_structured_validator_accepts_conforming_payload() -> None:
    """LIVE-STRUCTURED-02 — structured() validator accepts a conforming payload."""
    provider = live_provider_from_env()
    if provider is None:
        pytest.skip("live eval disabled")

    def _validator(v: object) -> str | None:
        if (
            isinstance(v, dict)
            and isinstance(v.get("status"), str)
            and isinstance(v.get("count"), int)
        ):
            return None
        return "wrong shape"

    result = await structured(
        provider,
        'Return only JSON: {"status": "ok", "count": 1}',
        validator=_validator,
        max_retries=1,
        temperature=0.0,
        max_tokens=64,
    )

    assert result.value["status"] == "ok"  # type: ignore[index]
    assert isinstance(result.value["count"], int)  # type: ignore[index]
    assert result.metadata["validated"] is True


# ---------------------------------------------------------------------------
# consensus()
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1",
    reason="set EXECUTIONKIT_LIVE_EVAL=1 to run live endpoint evals",
)
async def test_live_consensus_metadata_and_score() -> None:
    """LIVE-CONSENSUS-01 and LIVE-CONSENSUS-02 — metadata presence + score contract.

    Combines both design cases into a single API call to avoid double cost.
    """
    provider = live_provider_from_env()
    if provider is None:
        pytest.skip("live eval disabled")

    result = await consensus(
        provider,
        "What is 2 + 2? Answer with the digit only.",
        num_samples=3,
        temperature=0.0,
        max_tokens=16,
    )

    # LIVE-CONSENSUS-01: non-empty value and metadata presence
    assert isinstance(result.value, str)
    assert len(result.value.strip()) > 0
    assert 0.0 <= result.metadata["agreement_ratio"] <= 1.0
    assert isinstance(result.metadata["unique_responses"], int)
    assert result.metadata["unique_responses"] >= 1
    assert isinstance(result.metadata["tie_count"], int)

    # LIVE-CONSENSUS-02: score equals agreement_ratio
    assert result.score == pytest.approx(result.metadata["agreement_ratio"])


# ---------------------------------------------------------------------------
# react_loop()
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1",
    reason="set EXECUTIONKIT_LIVE_EVAL=1 to run live endpoint evals",
)
async def test_live_react_loop_tool_invocation_and_metadata() -> None:
    """LIVE-REACT-01 and LIVE-REACT-02 — tool invocation + full metadata contract.

    Combines both design cases into a single API call to avoid double cost.
    """
    provider = live_provider_from_env()
    if provider is None:
        pytest.skip("live eval disabled")

    async def _add(*, a: int, b: int) -> str:
        return str(a + b)

    add_tool = Tool(
        name="add",
        description="Add two integers",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
        execute=_add,
    )

    result = await react_loop(
        provider,
        "Use the add tool to compute 17 + 25. Report only the numeric result.",
        [add_tool],
        max_rounds=4,
        temperature=0.0,
        max_tokens=128,
    )

    # LIVE-REACT-01: tool was invoked and '42' appears in the final answer
    assert result.metadata["tool_calls_made"] >= 1
    assert "42" in result.value

    # LIVE-REACT-02: full metadata contract
    assert isinstance(result.metadata["rounds"], int)
    assert result.metadata["rounds"] >= 1
    assert isinstance(result.metadata["tool_calls_made"], int)
    assert result.metadata["tool_calls_made"] >= 0
    assert isinstance(result.metadata["truncated_responses"], int)
    assert result.metadata["truncated_responses"] >= 0
    assert isinstance(result.metadata["truncated_observations"], int)
    assert result.metadata["truncated_observations"] >= 0
    assert isinstance(result.metadata["messages_trimmed"], int)
    assert result.metadata["messages_trimmed"] >= 0
    assert result.score is None


# ---------------------------------------------------------------------------
# refine_loop()
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1",
    reason="set EXECUTIONKIT_LIVE_EVAL=1 to run live endpoint evals",
)
async def test_live_refine_loop_converges_and_score_history() -> None:
    """LIVE-REFINE-01 and LIVE-REFINE-02 — convergence + score_history contract.

    Uses a deterministic evaluator so no second LLM call is needed.
    Combines both design cases into a single API call.
    """
    provider = live_provider_from_env()
    if provider is None:
        pytest.skip("live eval disabled")

    async def _evaluator(text: str, _provider: object) -> float:
        # Any non-trivial response (>10 chars) scores 0.95 which exceeds
        # target_score=0.9, so the loop should converge on the first iteration.
        return 0.95 if len(text.strip()) > 10 else 0.3

    result = await refine_loop(
        provider,
        "Write one sentence about the sky.",
        evaluator=_evaluator,
        target_score=0.9,
        max_iterations=3,
        temperature=0.0,
        max_tokens=64,
    )

    # LIVE-REFINE-01: convergence and basic shape
    assert 0.0 <= result.score <= 1.0  # type: ignore[operator]
    assert isinstance(result.value, str)
    assert len(result.value.strip()) > 0
    assert result.metadata["converged"] is True
    assert isinstance(result.metadata["score_history"], list)
    assert len(result.metadata["score_history"]) >= 1

    # LIVE-REFINE-02: score_history is consistent with result.score
    score_history: list[float] = result.metadata["score_history"]
    assert score_history[0] == pytest.approx(result.score) or score_history[
        -1
    ] == pytest.approx(result.score)
    for entry in score_history:
        assert isinstance(entry, float)
        assert 0.0 <= entry <= 1.0
