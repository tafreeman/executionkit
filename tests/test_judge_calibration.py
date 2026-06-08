"""Opt-in live eval: default refine-loop judge calibration.

Verifies that the default LLM judge scores a well-formed factual answer
strictly higher than a minimal non-answer, using refine_loop at
max_iterations=0 (one generation, one evaluation — no refinement pass).

Gate: EXECUTIONKIT_LIVE_EVAL=1 plus EXECUTIONKIT_BASE_URL and
EXECUTIONKIT_MODEL.  The single test function is skipped unless all three
are set.
"""

from __future__ import annotations

import os

import pytest

from executionkit.evals import EvalCase, live_provider_from_env, run_eval_suite

# A well-formed factual prompt expected to elicit a high-quality answer.
_GOOD_PROMPT = (
    "Why is the sky blue? Explain the physics of Rayleigh scattering in 2-3 sentences."
)

# The same factual question prefixed to a directive that forces the model to
# respond with only "yes", producing a clearly low-quality answer.
_POOR_PROMPT = (
    "Why is the sky blue? Explain the physics of Rayleigh scattering in 2-3 sentences."
    "  Reply with only the word yes."
)


@pytest.mark.skipif(
    os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1",
    reason="set EXECUTIONKIT_LIVE_EVAL=1 to run live endpoint evals",
)
async def test_judge_calibration_good_beats_poor() -> None:
    """Default judge scores a high-quality answer strictly above a poor one."""
    provider = live_provider_from_env()
    if provider is None:
        pytest.skip("live eval disabled")

    # Shared dict populated sequentially by the first two eval cases.
    # run_eval_suite executes cases in order, so the ordering case safely reads
    # from this dict after both score cases have run.
    scores: dict[str, float] = {}

    async def run_good() -> float:
        from executionkit.patterns.refine_loop import refine_loop

        result = await refine_loop(
            provider,
            _GOOD_PROMPT,
            evaluator=None,
            max_iterations=0,
            temperature=0.0,
            max_tokens=256,
        )
        scores["good"] = result.score
        return result.score

    async def run_poor() -> float:
        from executionkit.patterns.refine_loop import refine_loop

        result = await refine_loop(
            provider,
            _POOR_PROMPT,
            evaluator=None,
            max_iterations=0,
            temperature=0.0,
            max_tokens=16,
        )
        scores["poor"] = result.score
        return result.score

    def check_good(score: float) -> bool | str | None:
        if not (0.0 <= score <= 1.0):
            return f"good score out of [0,1]: {score}"
        if score < 0.6:
            return f"good score too low (< 0.6): {score:.3f}"
        return None

    def check_poor(score: float) -> bool | str | None:
        if not (0.0 <= score <= 1.0):
            return f"poor score out of [0,1]: {score}"
        if score > 0.5:
            return f"poor score too high (> 0.5): {score:.3f}"
        return None

    def check_ordering(pair: tuple[float, float]) -> bool | str | None:
        good_score, poor_score = pair
        if good_score <= poor_score:
            return f"ordering violated: good={good_score:.3f} poor={poor_score:.3f}"
        return None

    cases = [
        EvalCase(
            name="judge-calibration/good-response-scores-high",
            run=run_good,
            check=check_good,
        ),
        EvalCase(
            name="judge-calibration/poor-response-scores-low",
            run=run_poor,
            check=check_poor,
        ),
        EvalCase(
            name="judge-calibration/ordering",
            # Scores dict is already populated by the two cases above.
            run=lambda: (scores.get("good", 0.0), scores.get("poor", 1.0)),
            check=check_ordering,
        ),
    ]

    report = await run_eval_suite(cases)

    if not report.passed:
        failure_lines = [f"  {f.name}: {f.reason}" for f in report.failures]
        pytest.fail(
            f"Judge calibration eval failed ({report.failed_count}/{report.total}):\n"
            + "\n".join(failure_lines)
        )
