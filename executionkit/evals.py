"""Small eval harness for deterministic and opt-in live checks."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from executionkit.provider import Provider

# Minimum accuracy required for LIVE / non-deterministic eval suites.
# Deterministic golden suites must still achieve 100% (report.passed).
# This named constant avoids magic numbers and makes the threshold auditable.
LIVE_EVAL_MIN_ACCURACY: float = 0.9

EvalRun: TypeAlias = Callable[[], Awaitable[Any] | Any]
EvalCheck: TypeAlias = Callable[[Any], bool | str | None]


def _readonly(metadata: Mapping[str, Any]) -> MappingProxyType[str, Any]:
    return MappingProxyType(dict(metadata))


@dataclass(frozen=True, slots=True)
class EvalCase:
    """A single eval case with a runner and a result check."""

    name: str
    run: EvalRun
    check: EvalCheck
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvalResult:
    """Outcome of a single eval case."""

    name: str
    passed: bool
    reason: str = ""
    metadata: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True, slots=True)
class EvalReport:
    """Aggregate eval report.

    Attributes:
        results: Per-case outcomes.
        min_accuracy: Optional accuracy threshold used by
            :func:`run_eval_suite` for live / non-deterministic suites.
            When set, callers gate on :attr:`accuracy_passed` instead of
            :attr:`passed` to allow a small number of tolerated failures.
    """

    results: tuple[EvalResult, ...]
    min_accuracy: float | None = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> bool:
        """True when *every* case passed (100% — required for deterministic suites)."""
        return all(result.passed for result in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed_count(self) -> int:
        return self.total - self.passed_count

    @property
    def failures(self) -> tuple[EvalResult, ...]:
        return tuple(result for result in self.results if not result.passed)

    @property
    def accuracy(self) -> float:
        """Fraction of cases that passed; 0.0 when the suite is empty."""
        if self.total == 0:
            return 0.0
        return self.passed_count / self.total

    @property
    def accuracy_passed(self) -> bool:
        """True when ``accuracy >= min_accuracy`` (live-suite gate).

        Falls back to :attr:`passed` when no ``min_accuracy`` was configured,
        so callers can always use this property as the single gate regardless
        of suite type.
        """
        if self.min_accuracy is None:
            return self.passed
        return self.accuracy >= self.min_accuracy

    def summary(self) -> str:
        """One-line human-readable result, e.g. '7/9 passed (77.8% accuracy)'."""
        return f"{self.passed_count}/{self.total} passed ({self.accuracy:.1%} accuracy)"


async def _run_case(case: EvalCase) -> EvalResult:
    try:
        maybe_output = case.run()
        output = (
            await maybe_output if inspect.isawaitable(maybe_output) else maybe_output
        )
        verdict = case.check(output)
    except Exception as exc:
        return EvalResult(
            name=case.name,
            passed=False,
            reason=f"{type(exc).__name__}: {exc}",
            metadata=_readonly(case.metadata),
        )

    if verdict is None or verdict is True:
        return EvalResult(
            name=case.name,
            passed=True,
            reason="passed",
            metadata=_readonly(case.metadata),
        )
    reason = "check returned False" if verdict is False else verdict
    return EvalResult(
        name=case.name,
        passed=False,
        reason=reason,
        metadata=_readonly(case.metadata),
    )


async def run_eval_suite(
    cases: Sequence[EvalCase],
    *,
    min_accuracy: float | None = None,
) -> EvalReport:
    """Run eval cases in order and return pass/fail results.

    Args:
        cases: Eval cases to run.
        min_accuracy: When provided, the report is considered passing when
            ``report.accuracy >= min_accuracy`` rather than requiring every
            case to pass (``report.passed``).  Use :data:`LIVE_EVAL_MIN_ACCURACY`
            for non-deterministic / live-provider suites that tolerate a small
            number of failures.  Deterministic golden suites should omit this
            parameter so they continue to require 100% pass rate via
            ``report.passed``.

    Returns:
        :class:`EvalReport` with per-case results.  The caller gates on either
        ``report.passed`` (deterministic) or
        ``report.accuracy >= min_accuracy`` (live).
    """
    return EvalReport(
        results=tuple([await _run_case(case) for case in cases]),
        min_accuracy=min_accuracy,
    )


def live_provider_from_env() -> Provider | None:
    """Build an opt-in live eval provider from EXECUTIONKIT_* env vars.

    Returns ``None`` unless ``EXECUTIONKIT_LIVE_EVAL=1``. When enabled,
    ``EXECUTIONKIT_BASE_URL`` and ``EXECUTIONKIT_MODEL`` are required;
    ``EXECUTIONKIT_API_KEY`` is optional and defaults to an empty string.
    """

    if os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1":
        return None

    base_url = os.getenv("EXECUTIONKIT_BASE_URL")
    model = os.getenv("EXECUTIONKIT_MODEL")
    missing = [
        name
        for name, value in (
            ("EXECUTIONKIT_BASE_URL", base_url),
            ("EXECUTIONKIT_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"{', '.join(missing)} required for live evals")

    return Provider(
        base_url=base_url or "",
        model=model or "",
        api_key=os.getenv("EXECUTIONKIT_API_KEY", ""),
    )
