"""Small eval harness for deterministic and opt-in live checks."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from executionkit.provider import Provider

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
    """Aggregate eval report."""

    results: tuple[EvalResult, ...]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> bool:
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


async def run_eval_suite(cases: Sequence[EvalCase]) -> EvalReport:
    """Run eval cases in order and return pass/fail results."""

    return EvalReport(results=tuple([await _run_case(case) for case in cases]))


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
