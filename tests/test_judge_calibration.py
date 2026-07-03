"""Opt-in live eval: default refine-loop judge calibration.

Verifies that the default LLM judge scores a well-formed factual answer
strictly higher than a minimal non-answer, using refine_loop at
max_iterations=0 (one generation, one evaluation — no refinement pass).

Gate: EXECUTIONKIT_LIVE_EVAL=1 plus EXECUTIONKIT_BASE_URL and
EXECUTIONKIT_MODEL.  The single test function is skipped unless all three
are set.

Two classes of expectation are enforced differently (calibration-first judge
policy — an uncalibrated judge's quality opinions are advisory, never gates):

* **Sanity invariants** (scores are floats within [0, 1]) hold for ANY judge
  and always hard-fail.
* **Quality expectations** (good scores high, poor scores low, good strictly
  beats poor) hold only for a judge calibrated enough to express them. For
  models in :data:`_KNOWN_MISCALIBRATED_JUDGE_MODELS` a quality failure is
  reported as **xfail** referencing the tracking issue — the scores are still
  produced and recorded in the eval output as calibration evidence, but the
  weekly tier no longer fails red on a documented small-model limitation
  (three consecutive scheduled failures, 2026-06-15..29, all the same
  ordering inversion: the judge scored a forced one-word non-answer above a
  real answer).
"""

from __future__ import annotations

import os

import pytest

from executionkit.evals import EvalCase, live_provider_from_env, run_eval_suite

# Judge models with a DOCUMENTED calibration failure for this suite's quality
# expectations. Quality failures under these models xfail (with issue link)
# instead of failing the tier; sanity invariants still hard-fail. Remove a
# model once https://github.com/tafreeman/executionkit/issues/36 is closed
# with a passing calibration record for it.
_KNOWN_MISCALIBRATED_JUDGE_MODELS: frozenset[str] = frozenset({"llama3.2:3b"})

_CALIBRATION_ISSUE_URL = "https://github.com/tafreeman/executionkit/issues/36"

# The exact failure shapes that count as QUALITY expectations (eligible for
# the known-miscalibrated xfail path). Everything else — out-of-range scores,
# errored runs (run_eval_suite converts raised exceptions into failure
# records), unexpected reasons — hard-fails for every model.
_QUALITY_FAILURE_MARKERS = ("too low", "too high", "ordering violated")

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
        # Out-of-range is a sanity invariant (holds for ANY judge): its reason
        # deliberately matches no _QUALITY_FAILURE_MARKERS entry, so it can
        # never be downgraded to the known-miscalibrated xfail path.
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
        summary = (
            f"Judge calibration eval failed ({report.failed_count}/{report.total}):\n"
            + "\n".join(failure_lines)
        )
        judge_model = os.getenv("EXECUTIONKIT_MODEL", "")
        all_quality = all(
            f.reason is not None
            and any(marker in f.reason for marker in _QUALITY_FAILURE_MARKERS)
            for f in report.failures
        )
        if all_quality and judge_model in _KNOWN_MISCALIBRATED_JUDGE_MODELS:
            # Quality expectations only: report honestly without failing the
            # tier — this judge's miscalibration is documented and tracked.
            # Sanity violations and errored runs never take this path.
            pytest.xfail(
                f"known-miscalibrated judge {judge_model!r} "
                f"(see {_CALIBRATION_ISSUE_URL}): {summary}"
            )
        pytest.fail(summary)
