"""Fast, network-free tests for scripts/claude_ci_eval.py.

The Claude-in-CI eval tier invokes a real CLI subprocess in production, so
these tests monkeypatch the single isolation point (``invoke_claude_cli``)
and otherwise exercise real logic: corpus loading, schema validation,
accuracy-floor arithmetic, and the skip-vs-gated exit-code decision.

No network access, no real ``claude`` process, no ANTHROPIC_API_KEY required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import claude_ci_eval as cli_eval  # noqa: E402 -- path setup must precede this import

# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def test_load_corpus_returns_all_failure_corpus_cases() -> None:
    """load_corpus() projects every EvalCase in FAILURE_CORPUS, in order."""
    from eval_failure_cases import FAILURE_CORPUS

    cases = cli_eval.load_corpus()

    assert len(cases) == len(FAILURE_CORPUS)
    assert [case.name for case in cases] == [ec.name for ec in FAILURE_CORPUS]


def test_load_corpus_cases_have_nonempty_fields() -> None:
    """Every projected case has a domain, description, and expected outcome."""
    cases = cli_eval.load_corpus()

    assert cases, "corpus must not be empty"
    for case in cases:
        assert case.domain
        assert case.description.strip()
        assert case.expected_outcome.strip()


# ---------------------------------------------------------------------------
# Schema validation — canned good/bad CLI responses
# ---------------------------------------------------------------------------


def _envelope(result: object) -> str:
    """Build a `claude --output-format json` style envelope around *result*."""
    return json.dumps({"result": result, "session_id": "abc123", "cost_usd": 0.001})


def test_validate_verdict_accepts_correct_response() -> None:
    """A well-formed 'correct' verdict parses into a JudgeVerdict."""
    inner = json.dumps(
        {
            "verdict": "correct",
            "reasoning": "Matches documented behaviour.",
            "confidence": 0.9,
        }
    )
    raw = _envelope(inner)

    verdict = cli_eval.validate_verdict(raw)

    assert verdict.verdict == "correct"
    assert verdict.reasoning == "Matches documented behaviour."
    assert verdict.confidence == pytest.approx(0.9)


def test_validate_verdict_accepts_incorrect_response_without_confidence() -> None:
    """confidence is optional; an 'incorrect' verdict without it still parses."""
    inner = json.dumps(
        {"verdict": "incorrect", "reasoning": "Disagrees with expectation."}
    )
    raw = _envelope(inner)

    verdict = cli_eval.validate_verdict(raw)

    assert verdict.verdict == "incorrect"
    assert verdict.confidence is None


def test_validate_verdict_accepts_dict_result_not_just_string() -> None:
    """The 'result' field may already be a dict (not a JSON-encoded string)."""
    raw = json.dumps(
        {"result": {"verdict": "correct", "reasoning": "ok"}, "session_id": "x"}
    )

    verdict = cli_eval.validate_verdict(raw)

    assert verdict.verdict == "correct"


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not json at all", id="top_level_not_json"),
        pytest.param(json.dumps({"no_result_field": True}), id="missing_result"),
        pytest.param(_envelope("also not json"), id="result_not_json"),
        pytest.param(_envelope(json.dumps(["a", "list"])), id="result_not_object"),
        pytest.param(
            _envelope(json.dumps({"verdict": "maybe", "reasoning": "x"})),
            id="verdict_not_in_enum",
        ),
        pytest.param(
            _envelope(json.dumps({"verdict": "correct"})), id="missing_reasoning"
        ),
        pytest.param(
            _envelope(json.dumps({"verdict": "correct", "reasoning": "  "})),
            id="blank_reasoning",
        ),
        pytest.param(
            _envelope(
                json.dumps({"verdict": "correct", "reasoning": "ok", "extra": "nope"})
            ),
            id="unexpected_key",
        ),
        pytest.param(
            _envelope(
                json.dumps(
                    {"verdict": "correct", "reasoning": "ok", "confidence": "high"}
                )
            ),
            id="confidence_not_a_number",
        ),
        pytest.param(
            _envelope(
                json.dumps({"verdict": "correct", "reasoning": "ok", "confidence": 1.5})
            ),
            id="confidence_out_of_range",
        ),
        pytest.param(
            _envelope(
                json.dumps(
                    {"verdict": "correct", "reasoning": "ok", "confidence": True}
                )
            ),
            id="confidence_is_bool_not_number",
        ),
    ],
)
def test_validate_verdict_rejects_malformed_responses(raw: str) -> None:
    """Every malformed shape raises ClaudeCliError rather than silently passing."""
    with pytest.raises(cli_eval.ClaudeCliError):
        cli_eval.validate_verdict(raw)


# ---------------------------------------------------------------------------
# Accuracy-floor logic
# ---------------------------------------------------------------------------


def _outcome(name: str, passed: bool) -> cli_eval.CaseOutcome:
    verdict = (
        cli_eval.JudgeVerdict(verdict="correct", reasoning="r")
        if passed
        else cli_eval.JudgeVerdict(verdict="incorrect", reasoning="r")
    )
    return cli_eval.CaseOutcome(case_name=name, passed=passed, verdict=verdict)


def test_compute_accuracy_all_passed() -> None:
    outcomes = tuple(_outcome(f"c{i}", True) for i in range(4))
    assert cli_eval.compute_accuracy(outcomes) == pytest.approx(1.0)


def test_compute_accuracy_partial() -> None:
    outcomes = (
        _outcome("a", True),
        _outcome("b", True),
        _outcome("c", False),
        _outcome("d", False),
    )
    assert cli_eval.compute_accuracy(outcomes) == pytest.approx(0.5)


def test_compute_accuracy_empty_is_zero() -> None:
    assert cli_eval.compute_accuracy(()) == 0.0


def test_accuracy_floor_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(cli_eval.ACCURACY_FLOOR_ENV_VAR, raising=False)
    assert cli_eval.accuracy_floor() == cli_eval.DEFAULT_ACCURACY_FLOOR


def test_accuracy_floor_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cli_eval.ACCURACY_FLOOR_ENV_VAR, "0.5")
    assert cli_eval.accuracy_floor() == pytest.approx(0.5)


def test_accuracy_floor_rejects_non_numeric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(cli_eval.ACCURACY_FLOOR_ENV_VAR, "not-a-number")
    with pytest.raises(ValueError, match="not a valid float"):
        cli_eval.accuracy_floor()


@pytest.mark.parametrize("bad_value", ["-0.1", "1.1"])
def test_accuracy_floor_rejects_out_of_range(
    monkeypatch: pytest.MonkeyPatch, bad_value: str
) -> None:
    monkeypatch.setenv(cli_eval.ACCURACY_FLOOR_ENV_VAR, bad_value)
    with pytest.raises(ValueError, match=r"within \[0\.0, 1\.0\]"):
        cli_eval.accuracy_floor()


# ---------------------------------------------------------------------------
# judge_case: CLI invocation mocked
# ---------------------------------------------------------------------------


def test_judge_case_passed_when_verdict_correct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = cli_eval.CorpusCase(
        name="FC-01:x", domain="json_extraction", description="d", expected_outcome="e"
    )

    def _fake_invoke(prompt: str, *, json_schema: dict) -> str:
        assert "FC-01:x" in prompt
        return _envelope(json.dumps({"verdict": "correct", "reasoning": "matches"}))

    monkeypatch.setattr(cli_eval, "invoke_claude_cli", _fake_invoke)

    outcome = cli_eval.judge_case(case)

    assert outcome.passed is True
    assert outcome.verdict is not None
    assert outcome.verdict.verdict == "correct"
    assert outcome.error == ""


def test_judge_case_failed_when_verdict_incorrect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = cli_eval.CorpusCase(
        name="FC-02:x", domain="json_extraction", description="d", expected_outcome="e"
    )
    monkeypatch.setattr(
        cli_eval,
        "invoke_claude_cli",
        lambda prompt, *, json_schema: _envelope(
            json.dumps({"verdict": "incorrect", "reasoning": "disagrees"})
        ),
    )

    outcome = cli_eval.judge_case(case)

    assert outcome.passed is False
    assert outcome.verdict is not None
    assert outcome.verdict.verdict == "incorrect"


def test_judge_case_failed_when_cli_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    case = cli_eval.CorpusCase(
        name="FC-03:x", domain="json_extraction", description="d", expected_outcome="e"
    )

    def _raise(prompt: str, *, json_schema: dict) -> str:
        raise cli_eval.ClaudeCliError("boom")

    monkeypatch.setattr(cli_eval, "invoke_claude_cli", _raise)

    outcome = cli_eval.judge_case(case)

    assert outcome.passed is False
    assert outcome.verdict is None
    assert "boom" in outcome.error


def test_judge_case_failed_when_response_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = cli_eval.CorpusCase(
        name="FC-04:x", domain="json_extraction", description="d", expected_outcome="e"
    )
    monkeypatch.setattr(
        cli_eval, "invoke_claude_cli", lambda prompt, *, json_schema: "not json"
    )

    outcome = cli_eval.judge_case(case)

    assert outcome.passed is False
    assert outcome.verdict is None
    assert outcome.error


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------


def test_format_table_includes_all_case_names() -> None:
    outcomes = (_outcome("FC-01:a", True), _outcome("FC-02:b", False))
    table = cli_eval.format_table(outcomes)

    assert "FC-01:a" in table
    assert "FC-02:b" in table
    assert "PASS" in table
    assert "FAIL" in table


def test_format_summary_reports_gate_passed() -> None:
    outcomes = tuple(_outcome(f"c{i}", True) for i in range(4))
    summary = cli_eval.format_summary(outcomes, floor=0.8)
    assert "PASSED" in summary
    assert "4/4" in summary


def test_format_summary_reports_gate_failed() -> None:
    outcomes = (_outcome("a", True), _outcome("b", False))
    summary = cli_eval.format_summary(outcomes, floor=0.8)
    assert "FAILED" in summary


# ---------------------------------------------------------------------------
# Skip-vs-gated exit codes (run() end-to-end, CLI invocation mocked)
# ---------------------------------------------------------------------------


def test_run_skips_cleanly_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ANTHROPIC_API_KEY, not gated: prints a skip message and exits 0."""
    monkeypatch.delenv(cli_eval.API_KEY_ENV_VAR, raising=False)
    monkeypatch.delenv(cli_eval.GATED_ENV_VAR, raising=False)

    exit_code = cli_eval.run([])

    assert exit_code == 0


def test_run_fails_when_gated_and_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ANTHROPIC_API_KEY, GATED=1: exits non-zero instead of skipping."""
    monkeypatch.delenv(cli_eval.API_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(cli_eval.GATED_ENV_VAR, "1")

    exit_code = cli_eval.run([])

    assert exit_code == 1


def test_run_skips_cleanly_without_cli_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API key present but `claude` not on PATH, not gated: skip, exit 0."""
    monkeypatch.setenv(cli_eval.API_KEY_ENV_VAR, "sk-fake")
    monkeypatch.delenv(cli_eval.GATED_ENV_VAR, raising=False)
    monkeypatch.setattr(cli_eval.shutil, "which", lambda _name: None)

    exit_code = cli_eval.run([])

    assert exit_code == 0


def test_run_passes_when_all_cases_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full happy path: prerequisites satisfied, CLI mocked to always agree."""
    monkeypatch.setenv(cli_eval.API_KEY_ENV_VAR, "sk-fake")
    monkeypatch.delenv(cli_eval.GATED_ENV_VAR, raising=False)
    monkeypatch.setattr(cli_eval.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        cli_eval,
        "invoke_claude_cli",
        lambda prompt, *, json_schema: _envelope(
            json.dumps({"verdict": "correct", "reasoning": "ok"})
        ),
    )

    exit_code = cli_eval.run([])

    assert exit_code == 0


def test_run_fails_when_accuracy_below_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """All cases judged incorrect: accuracy 0.0 is below any positive floor."""
    monkeypatch.setenv(cli_eval.API_KEY_ENV_VAR, "sk-fake")
    monkeypatch.delenv(cli_eval.GATED_ENV_VAR, raising=False)
    monkeypatch.setattr(cli_eval.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        cli_eval,
        "invoke_claude_cli",
        lambda prompt, *, json_schema: _envelope(
            json.dumps({"verdict": "incorrect", "reasoning": "nope"})
        ),
    )

    exit_code = cli_eval.run([])

    assert exit_code == 1


def test_run_reports_configuration_error_for_bad_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cli_eval.API_KEY_ENV_VAR, "sk-fake")
    monkeypatch.delenv(cli_eval.GATED_ENV_VAR, raising=False)
    monkeypatch.setattr(cli_eval.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setenv(cli_eval.ACCURACY_FLOOR_ENV_VAR, "not-a-number")

    exit_code = cli_eval.run([])

    assert exit_code == 1


# ---------------------------------------------------------------------------
# invoke_claude_cli: exercised directly with subprocess.run monkeypatched,
# to cover its own error paths without spawning a real process.
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_invoke_claude_cli_raises_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_eval.subprocess,
        "run",
        lambda *a, **k: _FakeCompletedProcess(1, "", "boom stderr"),
    )
    with pytest.raises(cli_eval.ClaudeCliError, match="exited 1"):
        cli_eval.invoke_claude_cli("prompt", json_schema={})


def test_invoke_claude_cli_raises_on_empty_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_eval.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "   ")
    )
    with pytest.raises(cli_eval.ClaudeCliError, match="no output"):
        cli_eval.invoke_claude_cli("prompt", json_schema={})


def test_invoke_claude_cli_raises_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess as real_subprocess

    def _raise_timeout(*args: object, **kwargs: object) -> None:
        raise real_subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(cli_eval.subprocess, "run", _raise_timeout)
    with pytest.raises(cli_eval.ClaudeCliError, match="timed out"):
        cli_eval.invoke_claude_cli("prompt", json_schema={})


def test_invoke_claude_cli_raises_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_os_error(*args: object, **kwargs: object) -> None:
        raise OSError("not found")

    monkeypatch.setattr(cli_eval.subprocess, "run", _raise_os_error)
    with pytest.raises(cli_eval.ClaudeCliError, match="failed to launch"):
        cli_eval.invoke_claude_cli("prompt", json_schema={})


def test_invoke_claude_cli_returns_stdout_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_eval.subprocess,
        "run",
        lambda *a, **k: _FakeCompletedProcess(0, '{"result": "ok"}'),
    )
    assert cli_eval.invoke_claude_cli("prompt", json_schema={}) == '{"result": "ok"}'
