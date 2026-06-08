"""Tests for EvalReport.accuracy and EvalReport.summary()."""

from __future__ import annotations

import dataclasses

import pytest

from executionkit.evals import EvalCase, EvalReport, EvalResult, run_eval_suite

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report(*passed_flags: bool) -> EvalReport:
    """Build an EvalReport from a sequence of pass/fail booleans."""
    results = tuple(
        EvalResult(name=f"case_{i}", passed=p) for i, p in enumerate(passed_flags)
    )
    return EvalReport(results=results)


# ---------------------------------------------------------------------------
# accuracy tests
# ---------------------------------------------------------------------------


def test_accuracy_all_pass() -> None:
    report = EvalReport(
        results=(EvalResult(name="a", passed=True), EvalResult(name="b", passed=True))
    )
    assert report.accuracy == 1.0


def test_accuracy_mixed() -> None:
    report = EvalReport(
        results=(
            EvalResult(name="a", passed=True),
            EvalResult(name="b", passed=False),
            EvalResult(name="c", passed=False),
        )
    )
    assert report.accuracy == pytest.approx(1 / 3)


def test_accuracy_empty() -> None:
    report = EvalReport(results=())
    assert report.accuracy == 0.0


def test_accuracy_all_fail() -> None:
    report = EvalReport(results=(EvalResult(name="a", passed=False),))
    assert report.accuracy == 0.0


def test_accuracy_is_float() -> None:
    report = EvalReport(results=(EvalResult(name="x", passed=True),))
    assert isinstance(report.accuracy, float)


# ---------------------------------------------------------------------------
# summary() tests
# ---------------------------------------------------------------------------


def test_summary_all_pass() -> None:
    report = EvalReport(
        results=(EvalResult(name="a", passed=True), EvalResult(name="b", passed=True))
    )
    assert report.summary() == "2/2 passed (100.0% accuracy)"


def test_summary_mixed() -> None:
    # 7 passing, 2 failing = 9 total
    report = _report(True, True, True, True, True, True, True, False, False)
    assert report.summary() == "7/9 passed (77.8% accuracy)"


def test_summary_empty() -> None:
    report = EvalReport(results=())
    assert report.summary() == "0/0 passed (0.0% accuracy)"


def test_summary_single_fail() -> None:
    report = EvalReport(results=(EvalResult(name="a", passed=False),))
    assert report.summary() == "0/1 passed (0.0% accuracy)"


# ---------------------------------------------------------------------------
# Existing-property regression
# ---------------------------------------------------------------------------


def test_existing_properties_unchanged() -> None:
    """Verify that all pre-existing EvalReport properties are unaffected."""
    report = EvalReport(
        results=(
            EvalResult(name="pass_case", passed=True, reason="ok"),
            EvalResult(name="fail_case", passed=False, reason="bad"),
        )
    )
    assert report.passed is False
    assert report.total == 2
    assert report.passed_count == 1
    assert report.failed_count == 1
    assert len(report.failures) == 1
    assert report.failures[0].name == "fail_case"


# ---------------------------------------------------------------------------
# Frozen-dataclass invariant
# ---------------------------------------------------------------------------


def test_report_still_frozen() -> None:
    report = EvalReport(results=(EvalResult(name="x", passed=True),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.results = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration: run_eval_suite produces a report with working accuracy
# ---------------------------------------------------------------------------


async def test_run_eval_suite_report_has_accuracy() -> None:
    report = await run_eval_suite(
        [
            EvalCase("p", lambda: None, lambda v: True),
            EvalCase("f", lambda: None, lambda v: False),
        ]
    )
    assert report.accuracy == pytest.approx(0.5)
