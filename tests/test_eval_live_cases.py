"""LIVE_CORPUS: a small, opt-in eval corpus run against a real provider.

Unlike ``tests/eval_datasets.py`` (deterministic, ``MockProvider``, always
runs in CI) and ``tests/eval_failure_cases.py`` (deterministic failure-mode
regressions), every case here calls a *real* model through
``executionkit.evals.live_provider_from_env()``. That hook returns ``None``
unless ``EXECUTIONKIT_LIVE_EVAL=1`` (plus ``EXECUTIONKIT_BASE_URL`` and
``EXECUTIONKIT_MODEL``) is set, so this module is safe to import and collect
with no credentials configured.

Marker: every test in this file carries ``@pytest.mark.live`` (registered in
``pyproject.toml``). Running the normal suite (``pytest`` with no ``-m``
filter, or explicitly ``pytest -m "not live"``) never touches these cases.
Running ``pytest -m live`` collects them but each one self-skips via
``pytest.skip()`` when ``live_provider_from_env()`` returns ``None`` — i.e.
"collected but skipped" locally / in normal CI, "collected and executed"
only where the live-eval env is fully configured (label-gated PR job or the
nightly/weekly schedule; see ``.github/workflows/ci.yml`` /
``.github/workflows/live-eval.yml``).
"""

from __future__ import annotations

from typing import Any

import pytest

from executionkit.evals import (
    LIVE_EVAL_MIN_ACCURACY,
    EvalCase,
    live_provider_from_env,
    run_eval_suite,
)

# ---------------------------------------------------------------------------
# Threshold
# ---------------------------------------------------------------------------
#
# LIVE_CORPUS gates on executionkit.evals.LIVE_EVAL_MIN_ACCURACY (currently
# 0.9) rather than a second, corpus-specific number. See the comment on that
# constant in executionkit/evals.py: it is a documented STARTING FLOOR, not a
# value observed from running this (or any) suite against a real endpoint —
# no such run has happened in this repo yet. Reusing the one committed
# constant keeps there from being two near-duplicate live thresholds that can
# silently drift apart; if LIVE_CORPUS ever needs a different bar than other
# live suites, give it its own named constant with its own justification
# instead of a bare literal here.


# ---------------------------------------------------------------------------
# Case builders
# ---------------------------------------------------------------------------
#
# Each case builds its own provider from live_provider_from_env() inside its
# `run` closure (rather than once at import time) so:
#   1. importing/collecting this module never requires the live env, and
#   2. a missing/misconfigured env is reported as a normal per-case failure
#      (via EvalCase's built-in exception handling in evals._run_case) rather
#      than an import-time crash.


def _case_structured_returns_requested_shape() -> EvalCase:
    async def run() -> Any:
        provider = live_provider_from_env()
        if provider is None:
            raise RuntimeError("live eval disabled (EXECUTIONKIT_LIVE_EVAL unset)")

        from executionkit.patterns.structured import structured

        result = await structured(
            provider,
            'Return only JSON with this exact shape: {"name": "alice", "age": 30}',
            max_retries=1,
            temperature=0.0,
            max_tokens=64,
        )
        return result.value

    def check(value: Any) -> str | None:
        if value != {"name": "alice", "age": 30}:
            return f"value mismatch: {value!r}"
        return None

    return EvalCase(
        name="live/structured-exact-shape",
        run=run,
        check=check,
        metadata={"category": "structured"},
    )


def _case_consensus_simple_arithmetic() -> EvalCase:
    async def run() -> Any:
        provider = live_provider_from_env()
        if provider is None:
            raise RuntimeError("live eval disabled (EXECUTIONKIT_LIVE_EVAL unset)")

        from executionkit.patterns.consensus import consensus

        result = await consensus(
            provider,
            "What is 2 + 2? Answer with the digit only.",
            num_samples=3,
            temperature=0.0,
            max_tokens=16,
        )
        return result.value

    def check(value: Any) -> str | None:
        if not isinstance(value, str) or "4" not in value:
            return f"expected '4' in consensus answer, got {value!r}"
        return None

    return EvalCase(
        name="live/consensus-simple-arithmetic",
        run=run,
        check=check,
        metadata={"category": "consensus"},
    )


def _case_react_loop_uses_tool() -> EvalCase:
    async def run() -> Any:
        provider = live_provider_from_env()
        if provider is None:
            raise RuntimeError("live eval disabled (EXECUTIONKIT_LIVE_EVAL unset)")

        from executionkit.patterns.react_loop import react_loop
        from executionkit.types import Tool

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
        return result

    def check(result: Any) -> str | None:
        if result.metadata["tool_calls_made"] < 1:
            return "tool was never invoked"
        if "42" not in result.value:
            return f"expected '42' in final answer, got {result.value!r}"
        return None

    return EvalCase(
        name="live/react-loop-uses-tool",
        run=run,
        check=check,
        metadata={"category": "react"},
    )


def _case_refine_loop_converges() -> EvalCase:
    async def run() -> Any:
        provider = live_provider_from_env()
        if provider is None:
            raise RuntimeError("live eval disabled (EXECUTIONKIT_LIVE_EVAL unset)")

        from executionkit.patterns.refine_loop import refine_loop

        async def _evaluator(text: str, _provider: object) -> float:
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
        return result

    def check(result: Any) -> str | None:
        if not result.metadata["converged"]:
            return "refine_loop did not converge"
        if result.score is None or result.score < 0.9:
            return f"score={result.score}, want >= 0.9"
        return None

    return EvalCase(
        name="live/refine-loop-converges",
        run=run,
        check=check,
        metadata={"category": "refine"},
    )


def live_corpus() -> list[EvalCase]:
    """Return the LIVE_CORPUS eval cases (one per pattern family)."""
    return [
        _case_structured_returns_requested_shape(),
        _case_consensus_simple_arithmetic(),
        _case_react_loop_uses_tool(),
        _case_refine_loop_converges(),
    ]


LIVE_CORPUS: tuple[EvalCase, ...] = tuple(live_corpus())


# ---------------------------------------------------------------------------
# Driver test
# ---------------------------------------------------------------------------


@pytest.mark.live
async def test_live_corpus_meets_accuracy_floor() -> None:
    """Run LIVE_CORPUS against a real provider and gate on the documented floor.

    Skipped (not failed) when ``live_provider_from_env()`` is disabled, so
    ``pytest -m live`` is collected-but-skipped in any environment without
    ``EXECUTIONKIT_LIVE_EVAL=1`` set (the normal path for local dev and the
    default CI job), and only executes for real where a label-gated PR job or
    the nightly/weekly schedule supplies the live-eval env.
    """
    if live_provider_from_env() is None:
        pytest.skip(
            "set EXECUTIONKIT_LIVE_EVAL=1 (+ BASE_URL/MODEL) to run LIVE_CORPUS"
        )

    report = await run_eval_suite(LIVE_CORPUS, min_accuracy=LIVE_EVAL_MIN_ACCURACY)

    if not report.accuracy_passed:
        failure_lines = [f"  {f.name}: {f.reason}" for f in report.failures]
        pytest.fail(
            f"LIVE_CORPUS below floor ({report.summary()}, "
            f"floor={LIVE_EVAL_MIN_ACCURACY:.0%}):\n" + "\n".join(failure_lines)
        )
