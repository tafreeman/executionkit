# ADR-013: Claude-in-CI Eval Tier via Headless CLI

**Date:** 2026-07-02
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** ExecutionKit already has two eval tiers: a deterministic golden/failure-corpus suite (ADR-006) that runs unconditionally in CI and asserts ExecutionKit's own code handles known failure modes correctly, and an opt-in live-provider tier (`live_provider_from_env`, `tests/test_eval_live_cases.py`, `.github/workflows/live-eval.yml`) that calls a real OpenAI-compatible endpoint. Neither tier answers a different question: does the corpus's own *expected outcome* for each failure case actually read as correct behaviour to a capable outside model, not just to ExecutionKit's own assertions? This decision adds that third tier using the Claude Code CLI in headless mode, distinct from and never merge-blocking alongside the other two.

---

## Context and Problem Statement

`tests/eval_failure_cases.py` (ADR-006) is a hand-curated, 13-case corpus
(`FC-01`-`FC-13`) proving ExecutionKit handles specific malformed-output,
injection, and bad-tool-argument scenarios gracefully. The deterministic
suite (`tests/test_eval_failure_corpus.py`) proves the code does what the
corpus's `check()` functions say it should — but the `check()` functions
themselves are written by the same people who wrote the code they check.
There was no independent, model-based signal that the corpus's documented
"expected outcome" for each case is actually the *right* behaviour, as
opposed to merely the behaviour that was implemented.

The team needed a way to get that independent signal without threatening the
things the first two tiers already protect: deterministic CI must stay
offline and 100%-reproducible (ADR-006), and no eval tier that depends on a
real model call may be allowed to block a merge (the existing `live-eval-pr`
gating pattern in `ci.yml`). Three questions had to be answered: which
invocation surface talks to Claude, how are its judgments structured and
verified so a malformed response cannot silently pass, and how is the tier
gated so it stays advisory.

## Decision Drivers

* ADR-004: zero new **runtime** dependencies. A CI/dev-only script may use
  subprocess and the standard library, but must not require the package
  itself to import an SDK.
* The existing live-eval gating pattern (label-gated PR trigger + unconditional
  weekly schedule + hard requirement that the job never becomes a required
  status check) is proven in this repo and should be reused, not reinvented.
* A model call is non-deterministic and can be slow, rate-limited, or briefly
  unavailable; none of that may ever fail a PR's required checks.
* The judge's output must be trusted only after structural validation — an
  unparsable or malformed CLI response must count as a failed case, not a
  crash and not a silently-ignored pass.
* The raw external-process boundary should be small and isolated so the rest
  of the script's logic (corpus loading, schema validation, accuracy-floor
  arithmetic, skip/gate decisions) is unit-testable without spawning a real
  process or spending API budget.

## Considered Options

* Option A: `claude -p` headless CLI, structured JSON output validated against a hand-rolled schema check, wired into a dedicated label/schedule-gated workflow
* Option B: Official `anthropic` Python SDK called directly from a script
* Option C: Fold Claude-judging into the existing `live_provider_from_env()` / `EXECUTIONKIT_LIVE_EVAL` live tier as another provider option

## Decision Outcome

Chosen option: **Option A — CLI-headless judging in `scripts/claude_ci_eval.py`**,
gated by a new `.github/workflows/claude-eval.yml` that mirrors the
label/schedule/never-required shape of `live-eval.yml` and the `live-eval-pr`
job in `ci.yml`.

**Why CLI-headless over the SDK (Option B):** the Claude Code CLI's
`--output-format json` plus `--json-schema` flags already provide exactly
the constrained-output contract this tier needs (a single structured verdict
per case), with zero new dependency footprint anywhere — not even in
`dev` extras. Calling `anthropic`'s Python SDK directly would add a new dev
dependency to `pyproject.toml` purely to duplicate what the CLI already does
as an external process, and would blur the line between "ExecutionKit code
that imports an SDK" and "CI tooling that shells out to a tool a developer
already has installed for other tasks." The CLI is the correct-weight choice
for a CI-only judge; it is not, and should not become, a pattern for
ExecutionKit's own runtime code to depend on Claude specifically (the
library remains provider-agnostic per ADR-003).

**Why a distinct tier rather than folding into the live-provider tier
(Option C):** `live_provider_from_env()` builds an OpenAI-compatible
`Provider` and drives it through ExecutionKit's own patterns — it answers
"does ExecutionKit's code work against a real endpoint?" A Claude-CLI judge
answers a different question — "does an independent, capable model agree the
corpus's documented expectations are correct?" — and does so by invoking an
external CLI process, not the library's `Provider` protocol at all. Merging
the two would conflate two different eval semantics behind one env-var
switch and require `Provider` to grow a CLI-subprocess backend it has no
other reason to support.

**Why label/schedule gating, mirroring the live-eval pattern:** the repo
already has a proven, reviewed shape for "opt-in real-external-call eval that
must never block a merge" — PR label trigger, `workflow_dispatch`, and an
unconditional weekly schedule, with an explicit comment warning that the job
must never be added to required status checks. Reusing that shape rather than
inventing a new gating convention keeps the contributor mental model
consistent across all three eval tiers.

**What the schema validates:** the verdict payload is a JSON object with
exactly three allowed keys — `verdict` (enum `"correct"`/`"incorrect"`,
required), `reasoning` (non-empty string, required), and `confidence`
(number in `[0.0, 1.0]`, optional). `additionalProperties` is rejected.
Validation is hand-rolled (`scripts/claude_ci_eval.py::validate_verdict`)
rather than using the `jsonschema` optional extra, because the schema is
small, fixed, and known at authoring time — pulling in a schema-validation
library for three keys would be disproportionate, and the script is
stdlib-only by design (no new dependency, dev or runtime). Any parse failure,
missing/extra key, or out-of-enum value raises `ClaudeCliError` and the case
is scored as failed rather than crashing the run.

### Consequences

* Good: an independent, model-based check on the *correctness* of the
  corpus's documented expectations exists, without threatening the
  determinism or offline guarantee of the ADR-006 golden suite.
* Good: zero new runtime or dev dependency — `scripts/claude_ci_eval.py`
  uses only `argparse`, `json`, `os`, `shutil`, `subprocess`, `sys`,
  `dataclasses`, and `pathlib`.
* Good: the CLI invocation is isolated in one function
  (`invoke_claude_cli`), so the fast test suite (`tests/test_claude_ci_eval.py`)
  covers corpus loading, schema validation, accuracy-floor logic, and the
  skip-vs-gated exit-code decision entirely by monkeypatching that one
  function — no network access, no real CLI process, no API key required to
  keep the 80% coverage floor green.
* Good: this tier can never fail a required check — it runs only on the
  `run-claude-eval` PR label, manual dispatch, or the weekly schedule, and is
  documented as never eligible for branch-protection required-status status.
* Neutral: like the existing live tiers, this adds a second env-derived gate
  shape (`CLAUDE_CI_EVAL_GATED` mirrors the opt-in/gated semantics of
  `EXECUTIONKIT_LIVE_EVAL`, but is a distinct variable because the
  prerequisites differ — `ANTHROPIC_API_KEY` and the `claude` executable on
  `PATH`, not `EXECUTIONKIT_BASE_URL`/`EXECUTIONKIT_MODEL`).
* Bad: this tier's judgments depend on the Claude Code CLI's own
  `--json-schema` structured-output behaviour, an external tool this repo
  does not control the release cadence of. Mitigated by validating every
  response structurally regardless of what the CLI claims to guarantee.
* Bad: as with `LIVE_EVAL_MIN_ACCURACY` (ADR alongside `executionkit/evals.py`),
  `DEFAULT_ACCURACY_FLOOR` (0.8) is a documented starting floor, not a value
  derived from an observed run — this tier has not executed against a real
  endpoint yet in this repo. Revisit once `claude-eval.yml` has run enough
  times on the weekly schedule to justify a data-backed threshold.

## Pros and Cons of the Options

### Option A: CLI-headless, hand-rolled schema validation

* **Good:** zero new dependency anywhere in `pyproject.toml`.
* **Good:** reuses the CLI a Claude Code contributor already has installed.
* **Good:** isolatable, mockable invocation boundary.
* **Bad:** couples the tier to the CLI's `--json-schema` support and output envelope shape.

### Option B: Official `anthropic` SDK

* **Good:** typed request/response objects; no subprocess/text-parsing layer.
* **Bad:** adds a new dev dependency purely for a CI-only judge script.
* **Bad:** duplicates functionality the CLI already exposes via structured output.

### Option C: Fold into `live_provider_from_env()`

* **Good:** one less workflow file; reuses existing `EXECUTIONKIT_LIVE_EVAL` plumbing.
* **Bad:** conflates two different eval semantics (library-code-against-endpoint vs. external-judge-of-corpus-correctness) behind one switch.
* **Bad:** would require `Provider` to grow a CLI-subprocess transport it has no other reason to support, weakening the OpenAI-compatible `Provider` contract (ADR-003).
