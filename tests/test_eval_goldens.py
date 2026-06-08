"""Golden eval suite integration test.

Runs all cases from ``eval_datasets.golden_cases()`` through
``run_eval_suite`` and asserts every case passes.
"""

from __future__ import annotations


async def test_golden_eval_suite_all_pass() -> None:
    from eval_datasets import golden_cases

    from executionkit.evals import run_eval_suite

    cases = golden_cases()
    assert len(cases) >= 9, f"Expected >= 9 golden cases, got {len(cases)}"

    report = await run_eval_suite(cases)

    assert report.passed is True, f"{report.failed_count} case(s) failed: " + ", ".join(
        f"{f.name}: {f.reason}" for f in report.failures
    )
    assert report.failed_count == 0
