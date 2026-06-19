"""Small eval harness for deterministic and opt-in live checks."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeAlias

from executionkit.provider import Provider

if TYPE_CHECKING:
    from executionkit.kit import Kit
    from executionkit.types import PatternResult

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
class Turn:
    """One turn of a multi-turn :class:`ConversationScript`.

    Attributes:
        user: The user text sent to :meth:`Kit.turn` for this turn.
        check: An :data:`EvalCheck` applied to the ``PatternResult[str]`` that
            ``kit.turn`` returns. Returning ``None``/``True``/``""`` passes the
            turn; returning ``False`` or a non-empty string fails it (the string
            becomes the failure reason).
    """

    user: str
    check: EvalCheck


@dataclass(frozen=True, slots=True)
class ConversationScript:
    """A named, ordered sequence of conversational turns to evaluate.

    Run via :func:`run_conversation_script`, which drives each turn through a
    single :class:`~executionkit.kit.Kit` so conversation state carries across
    turns.

    Attributes:
        name: Identifier used to label each turn's :class:`EvalResult`
            (``f"{name}[{i}]"`` for turn ``i``).
        turns: The turns to run, in order.
    """

    name: str
    turns: tuple[Turn, ...]


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


def _verdict_to_result(
    name: str,
    verdict: bool | str | None,
    metadata: MappingProxyType[str, Any],
) -> EvalResult:
    """Normalize an :data:`EvalCheck` verdict into an :class:`EvalResult`.

    Mapping: ``None``/``True``/``""`` pass; ``False`` fails with
    ``"check returned False"``; any other string fails with that string as the
    reason.
    """
    if verdict is None or verdict is True or verdict == "":
        return EvalResult(name=name, passed=True, reason="passed", metadata=metadata)
    reason = "check returned False" if verdict is False else verdict
    return EvalResult(name=name, passed=False, reason=reason, metadata=metadata)


async def _run_case(case: EvalCase) -> EvalResult:
    metadata = _readonly(case.metadata)
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
            metadata=metadata,
        )

    return _verdict_to_result(case.name, verdict, metadata)


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


async def run_conversation_script(
    script: ConversationScript,
    kit: Kit,
) -> EvalReport:
    """Drive a multi-turn :class:`ConversationScript` through a single ``Kit``.

    Each turn is sent via ``kit.turn(turn.user)``; because the same *kit*
    carries conversation state across calls, later turns see the transcript of
    earlier ones. The :class:`PatternResult` returned by each ``turn`` is passed
    to that turn's :data:`EvalCheck`, and the verdict is normalized exactly like
    :func:`run_eval_suite` does (``None``/``True``/``""`` pass; ``False`` and
    other strings fail). Any exception raised by ``kit.turn`` or the check is
    captured as a failed :class:`EvalResult` rather than propagated, so one bad
    turn does not abort the remaining turns.

    Args:
        script: The named sequence of turns to evaluate.
        kit: A :class:`~executionkit.kit.Kit` session whose provider satisfies
            :class:`~executionkit.provider.ToolCallingProvider`. State accrues
            on this kit as the script runs.

    Returns:
        An :class:`EvalReport` with one :class:`EvalResult` per turn, each named
        ``f"{script.name}[{i}]"``. No ``min_accuracy`` is set, so the report
        gates on a 100% pass rate via :attr:`EvalReport.passed`.
    """
    results: list[EvalResult] = []
    empty_metadata: MappingProxyType[str, Any] = MappingProxyType({})
    for index, turn in enumerate(script.turns):
        name = f"{script.name}[{index}]"
        try:
            result: PatternResult[str] = await kit.turn(turn.user)
            verdict = turn.check(result)
        except Exception as exc:
            results.append(
                EvalResult(
                    name=name,
                    passed=False,
                    reason=f"{type(exc).__name__}: {exc}",
                    metadata=empty_metadata,
                )
            )
            continue
        results.append(_verdict_to_result(name, verdict, empty_metadata))
    return EvalReport(results=tuple(results))


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
