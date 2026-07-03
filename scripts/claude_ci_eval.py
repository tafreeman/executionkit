#!/usr/bin/env python3
"""Claude-in-CI eval: judge the failure corpus with the Claude Code CLI.

This is a *distinct* eval tier from the deterministic golden suite
(``tests/test_eval_failure_corpus.py``, which runs unconditionally in CI) and
from the opt-in live-provider tiers (``executionkit.evals.live_provider_from_env``,
``tests/test_eval_live_cases.py``). Those tiers prove ExecutionKit's own code
handles a failure gracefully. This tier asks a real Claude model, via the
headless Claude Code CLI (``claude -p``), to *judge* each corpus case against
its documented expected outcome — evidence that the corpus's expectations
read the way a model actually reasons about them, not just the way
ExecutionKit's assertions say they should.

Design (see docs/adr/013-claude-in-ci-eval.md for the full rationale):

* Stdlib-only. No new runtime or dev dependency — the CLI is invoked as a
  subprocess, and its structured JSON output is parsed with ``json``.
* The raw CLI invocation lives in exactly one small function,
  :func:`invoke_claude_cli`, so tests can monkeypatch it and never spawn a
  real process or spend real API budget.
* Every model response is validated against a strict, minimal verdict schema
  (:func:`validate_verdict`) before it is trusted. A response that doesn't
  parse or doesn't match the schema counts as a failed case, not a crash.
* Absent ``ANTHROPIC_API_KEY`` or the ``claude`` executable, the script
  prints a one-line skip message and exits 0 — *unless* the gate flag
  (:data:`GATED_ENV_VAR`) is set to ``"1"``, in which case missing
  prerequisites are a hard failure. This mirrors the opt-in/gated shape of
  ``EXECUTIONKIT_LIVE_EVAL`` in ``executionkit.evals.live_provider_from_env``:
  normal CI runs (and the weekly schedule with no secret configured) skip
  cleanly; a run that explicitly opts in and is missing what it needs fails
  loudly instead of silently reporting a false "all green."
* Exit code is non-zero only when measured accuracy against the corpus's
  expected outcomes falls below :data:`DEFAULT_ACCURACY_FLOOR` (overridable
  via :data:`ACCURACY_FLOOR_ENV_VAR`). A single flaky model call cannot fail
  the run outright — see the accuracy-floor logic in :func:`compute_accuracy`.

This script is intentionally never wired into a required GitHub branch
protection check (see .github/workflows/claude-eval.yml) — a model-judged
tier is advisory, not merge-blocking.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# Named constants — no magic numbers.
# ---------------------------------------------------------------------------

#: Env var that opts the run into hard-failing when prerequisites (API key,
#: CLI on PATH) are missing, instead of the default clean skip. Mirrors
#: FSE's EVAL_INTENT_GATED / ExecutionKit's own EXECUTIONKIT_LIVE_EVAL shape:
#: unset (or any value other than "1") -> best-effort skip; "1" -> require it.
GATED_ENV_VAR: Final[str] = "CLAUDE_CI_EVAL_GATED"

#: Env var overriding the minimum required accuracy (0.0-1.0). Unset falls
#: back to DEFAULT_ACCURACY_FLOOR.
ACCURACY_FLOOR_ENV_VAR: Final[str] = "CLAUDE_CI_EVAL_MIN_ACCURACY"

#: Default minimum fraction of corpus cases the model must judge correctly
#: for the run to be considered passing. Documented starting floor (like
#: executionkit.evals.LIVE_EVAL_MIN_ACCURACY) — not derived from an observed
#: run, since this tier has not executed against a real endpoint yet in this
#: repo. Revisit once claude-eval.yml has run enough times to justify a
#: data-backed value.
DEFAULT_ACCURACY_FLOOR: Final[float] = 0.8

#: Required API key env var. Its mere presence (not validity) gates the run.
API_KEY_ENV_VAR: Final[str] = "ANTHROPIC_API_KEY"

#: Executable name resolved via shutil.which().
CLAUDE_EXECUTABLE: Final[str] = "claude"

#: Per-invocation subprocess timeout (seconds). A hung CLI call must not hang
#: CI indefinitely.
CLI_TIMEOUT_SECONDS: Final[int] = 120

#: Claude Code CLI model used for judging — the current Haiku snapshot, pinned
#: by date so judge behaviour doesn't drift under an alias. Kept small/cheap:
#: this tier runs a fixed small corpus, not a general benchmark.
JUDGE_MODEL: Final[str] = "claude-haiku-4-5-20251001"

#: Verdict values the judge schema accepts.
VALID_VERDICTS: Final[frozenset[str]] = frozenset({"correct", "incorrect"})

#: JSON Schema passed to `claude --json-schema` constraining the verdict
#: shape. Kept intentionally minimal: a verdict, a one-line reasoning string,
#: and a self-reported confidence used only for the printed report (not for
#: pass/fail, which is decided by comparing `verdict` to the corpus's
#: expected outcome).
VERDICT_JSON_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": sorted(VALID_VERDICTS)},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["verdict", "reasoning"],
    "additionalProperties": False,
}

#: Column widths for the printed per-case table.
_NAME_COL_WIDTH: Final[int] = 46
_VERDICT_COL_WIDTH: Final[int] = 10


class ClaudeCliError(RuntimeError):
    """Raised when the Claude CLI invocation fails or returns malformed output."""


@dataclass(frozen=True, slots=True)
class CorpusCase:
    """One case drawn from the committed failure corpus for CLI judging.

    A deliberately narrow projection of ``executionkit.evals.EvalCase``: the
    CLI judge is given a natural-language description of the failure mode and
    the expected outcome, not the executable ``run``/``check`` callables
    (those already run, and pass, in the deterministic golden suite).
    """

    name: str
    domain: str
    description: str
    expected_outcome: str


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """A validated verdict returned by the Claude CLI for one corpus case."""

    verdict: str
    reasoning: str
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """The result of judging a single corpus case: verdict versus expectation."""

    case_name: str
    passed: bool
    verdict: JudgeVerdict | None
    error: str = ""


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def load_corpus() -> tuple[CorpusCase, ...]:
    """Load the committed failure corpus and project it into CorpusCase rows.

    Imports ``tests.eval_failure_cases.FAILURE_CORPUS`` (the same corpus the
    deterministic golden suite runs) so this script never maintains a second,
    drifting copy of the case list. Each ``EvalCase.name`` follows the
    ``FC-NN:domain:slug`` convention; the human-readable description is
    derived from the docstring of the case's ``run`` callable, falling back
    to the slug when no docstring is present.
    """
    repo_root = Path(__file__).resolve().parent.parent
    tests_dir = str(repo_root / "tests")
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    from eval_failure_cases import (  # type: ignore[import-not-found]
        FAILURE_CORPUS,
    )

    cases: list[CorpusCase] = []
    for eval_case in FAILURE_CORPUS:
        domain = str(eval_case.metadata.get("domain", "unknown"))
        docstring = eval_case.run.__doc__
        description = docstring.strip() if docstring else eval_case.name
        expected_outcome = (
            eval_case.check.__doc__.strip()
            if eval_case.check.__doc__
            else "The documented failure mode is handled gracefully (no crash)."
        )
        cases.append(
            CorpusCase(
                name=eval_case.name,
                domain=domain,
                description=description,
                expected_outcome=expected_outcome,
            )
        )
    return tuple(cases)


# ---------------------------------------------------------------------------
# CLI invocation — isolated in ONE function so tests can monkeypatch it.
# ---------------------------------------------------------------------------


def invoke_claude_cli(prompt: str, *, json_schema: dict[str, Any]) -> str:
    """Run ``claude -p`` headless with structured JSON output and return stdout.

    This is the *only* function in the module that spawns a subprocess or
    touches the network. Tests replace it with a stub (see
    ``tests/test_claude_ci_eval.py``) so the rest of the module's logic
    (schema validation, accuracy floor, skip/gate decisions) is exercised
    without ever calling a real model.

    Raises:
        ClaudeCliError: the CLI exited non-zero, timed out, or produced no
            output on stdout.
    """
    command = [
        CLAUDE_EXECUTABLE,
        "-p",
        prompt,
        "--model",
        JUDGE_MODEL,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(json_schema),
    ]
    try:
        # S603 is ignored for this file in pyproject per-file-ignores: fixed
        # argv, no shell, executable resolved via shutil.which upstream.
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCliError(
            f"claude CLI timed out after {CLI_TIMEOUT_SECONDS}s"
        ) from exc
    except OSError as exc:
        raise ClaudeCliError(f"failed to launch claude CLI: {exc}") from exc

    if completed.returncode != 0:
        raise ClaudeCliError(
            f"claude CLI exited {completed.returncode}: {completed.stderr.strip()}"
        )
    if not completed.stdout.strip():
        raise ClaudeCliError("claude CLI produced no output on stdout")
    return completed.stdout


def _build_prompt(case: CorpusCase) -> str:
    """Build the judging prompt for one corpus case."""
    return (
        "You are auditing a single entry in a committed model-failure test "
        "corpus for an LLM reasoning-patterns library. Judge whether the "
        "library's documented behaviour is the CORRECT way to handle this "
        "failure mode.\n\n"
        f"Domain: {case.domain}\n"
        f"Case: {case.name}\n"
        f"Failure mode under test: {case.description}\n"
        f"Library's documented expected outcome: {case.expected_outcome}\n\n"
        'Respond with verdict="correct" if the documented expected outcome '
        "is the right way to handle this failure mode, or "
        'verdict="incorrect" if it is not. Give a one-sentence reasoning."'
    )


# ---------------------------------------------------------------------------
# Schema validation — stdlib-only structural check (no jsonschema dependency;
# the schema this script uses is small and fixed, so a hand-rolled validator
# is proportionate and keeps the zero-runtime-dependency / stdlib-only goal
# intact for dev tooling too).
# ---------------------------------------------------------------------------


def validate_verdict(raw_response_text: str) -> JudgeVerdict:
    """Parse and validate one CLI response against the verdict schema.

    The Claude CLI's ``--output-format json`` wraps the model's structured
    answer inside an envelope (a ``result`` field, alongside cost/session
    metadata); when ``--json-schema`` is supplied, ``result`` is itself a
    JSON string matching that schema. This function unwraps both layers and
    validates the inner object against :data:`VERDICT_JSON_SCHEMA`.

    Raises:
        ClaudeCliError: the envelope or inner payload is not valid JSON, or
            the inner payload does not match the verdict schema.
    """
    try:
        envelope = json.loads(raw_response_text)
    except json.JSONDecodeError as exc:
        raise ClaudeCliError(f"CLI output is not valid JSON: {exc}") from exc

    inner_raw = envelope.get("result") if isinstance(envelope, dict) else None
    if inner_raw is None:
        raise ClaudeCliError("CLI output envelope has no 'result' field")

    if isinstance(inner_raw, str):
        try:
            payload = json.loads(inner_raw)
        except json.JSONDecodeError as exc:
            raise ClaudeCliError(f"CLI 'result' is not valid JSON: {exc}") from exc
    elif isinstance(inner_raw, dict):
        payload = inner_raw
    else:
        raise ClaudeCliError(
            f"CLI 'result' has unexpected type {type(inner_raw).__name__}"
        )

    return _validate_verdict_payload(payload)


def _validate_verdict_payload(payload: Any) -> JudgeVerdict:
    """Structurally validate *payload* against VERDICT_JSON_SCHEMA."""
    if not isinstance(payload, dict):
        raise ClaudeCliError(
            f"verdict payload must be an object, got {type(payload).__name__}"
        )

    extra_keys = set(payload) - {"verdict", "reasoning", "confidence"}
    if extra_keys:
        raise ClaudeCliError(
            f"verdict payload has unexpected keys: {sorted(extra_keys)}"
        )

    verdict = payload.get("verdict")
    if not isinstance(verdict, str) or verdict not in VALID_VERDICTS:
        raise ClaudeCliError(
            f"verdict must be one of {sorted(VALID_VERDICTS)}, got {verdict!r}"
        )

    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ClaudeCliError("reasoning must be a non-empty string")

    confidence_raw = payload.get("confidence")
    confidence: float | None = None
    if confidence_raw is not None:
        if isinstance(confidence_raw, bool) or not isinstance(
            confidence_raw, (int, float)
        ):
            raise ClaudeCliError(
                f"confidence must be a number, got {type(confidence_raw).__name__}"
            )
        confidence = float(confidence_raw)
        if not (0.0 <= confidence <= 1.0):
            raise ClaudeCliError(
                f"confidence must be within [0.0, 1.0], got {confidence}"
            )

    return JudgeVerdict(verdict=verdict, reasoning=reasoning, confidence=confidence)


# ---------------------------------------------------------------------------
# Judging + aggregation
# ---------------------------------------------------------------------------


def judge_case(case: CorpusCase) -> CaseOutcome:
    """Invoke the CLI for one case and score it against the expected outcome.

    Every corpus case's documented expected outcome is, by construction
    (ADR-006), the behaviour ExecutionKit actually implements — so the
    correct judge verdict is always "correct". A case counts as passed when
    the model's verdict is "correct"; any other verdict, or any error raised
    while invoking or validating the CLI response, counts as failed (but
    never raises out of this function — failures are data, not crashes).
    """
    try:
        raw = invoke_claude_cli(_build_prompt(case), json_schema=VERDICT_JSON_SCHEMA)
        verdict = validate_verdict(raw)
    except ClaudeCliError as exc:
        return CaseOutcome(
            case_name=case.name, passed=False, verdict=None, error=str(exc)
        )

    passed = verdict.verdict == "correct"
    return CaseOutcome(case_name=case.name, passed=passed, verdict=verdict)


def compute_accuracy(outcomes: tuple[CaseOutcome, ...]) -> float:
    """Fraction of *outcomes* that passed; 0.0 for an empty outcome set."""
    if not outcomes:
        return 0.0
    return sum(1 for outcome in outcomes if outcome.passed) / len(outcomes)


def accuracy_floor() -> float:
    """Resolve the minimum required accuracy from env, falling back to the default.

    An unparsable or out-of-range override is a configuration error worth
    surfacing loudly (not silently ignored), since it changes the pass/fail
    gate.
    """
    raw = os.environ.get(ACCURACY_FLOOR_ENV_VAR)
    if raw is None or raw.strip() == "":
        return DEFAULT_ACCURACY_FLOOR
    try:
        floor = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{ACCURACY_FLOOR_ENV_VAR}={raw!r} is not a valid float"
        ) from exc
    if not (0.0 <= floor <= 1.0):
        raise ValueError(f"{ACCURACY_FLOOR_ENV_VAR}={raw!r} must be within [0.0, 1.0]")
    return floor


def is_gated() -> bool:
    """True when the run has opted into hard-failing on missing prerequisites."""
    return os.environ.get(GATED_ENV_VAR) == "1"


def prerequisites_missing() -> str | None:
    """Return a human-readable reason prerequisites are missing, or None if OK."""
    if not os.environ.get(API_KEY_ENV_VAR):
        return f"{API_KEY_ENV_VAR} is not set"
    if shutil.which(CLAUDE_EXECUTABLE) is None:
        return f"'{CLAUDE_EXECUTABLE}' executable not found on PATH"
    return None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def format_table(outcomes: tuple[CaseOutcome, ...]) -> str:
    """Render a per-case pass/fail table as a printable string."""
    header = f"{'case':<{_NAME_COL_WIDTH}} {'verdict':<{_VERDICT_COL_WIDTH}} detail"
    lines = [header, "-" * len(header)]
    for outcome in outcomes:
        status = "PASS" if outcome.passed else "FAIL"
        if outcome.verdict is not None:
            detail = outcome.verdict.reasoning
        else:
            detail = outcome.error
        lines.append(
            f"{outcome.case_name:<{_NAME_COL_WIDTH}} "
            f"{status:<{_VERDICT_COL_WIDTH}} "
            f"{detail}"
        )
    return "\n".join(lines)


def format_summary(outcomes: tuple[CaseOutcome, ...], *, floor: float) -> str:
    """Render the final pass/fail summary line."""
    accuracy = compute_accuracy(outcomes)
    passed_count = sum(1 for outcome in outcomes if outcome.passed)
    gate = "PASSED" if accuracy >= floor else "FAILED"
    return (
        f"{passed_count}/{len(outcomes)} passed "
        f"({accuracy:.1%} accuracy, floor {floor:.1%}) -> gate {gate}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(argv: list[str] | None = None) -> int:
    """Run the Claude-in-CI eval end-to-end; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    missing_reason = prerequisites_missing()
    if missing_reason is not None:
        if is_gated():
            print(
                f"claude-ci-eval: GATED and prerequisites missing: {missing_reason}",
                file=sys.stderr,
            )
            return 1
        print(
            f"claude-ci-eval: skipping ({missing_reason}); "
            f"set {GATED_ENV_VAR}=1 to fail instead."
        )
        return 0

    try:
        floor = accuracy_floor()
    except ValueError as exc:
        print(f"claude-ci-eval: configuration error: {exc}", file=sys.stderr)
        return 1

    corpus = load_corpus()
    outcomes = tuple(judge_case(case) for case in corpus)

    print(format_table(outcomes))
    print()
    print(format_summary(outcomes, floor=floor))

    accuracy = compute_accuracy(outcomes)
    return 0 if accuracy >= floor else 1


if __name__ == "__main__":
    sys.exit(run())
