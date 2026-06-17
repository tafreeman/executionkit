# ADR-006: Curated Failure-Corpus Eval Methodology

**Date:** 2026-06-08
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** The v0.2 eval harness added two parallel test suites: a golden dataset of expected happy-path outputs (`tests/eval_datasets.py`) and a separate curated corpus of real-world model-output failure modes (`tests/eval_failure_cases.py`). The team chose to maintain these as a named, hand-curated list of `EvalCase` objects rather than as property-based tests or fuzzer-driven cases.

---

## Context and Problem Statement

ExecutionKit's patterns (`structured`, `refine_loop`, `react_loop`, `consensus`) must handle malformed LLM outputs gracefully — no crash, correct error or repair behaviour. Model outputs regularly violate expected formats in specific ways: JSON with trailing commas, unterminated objects, bare integers, oversized tool observations, prompt-injection payloads in scores, and hostile token-usage values from buggy endpoints.

The team needed to decide how to capture and assert on these failure modes in CI. Three approaches were available: a property-based fuzzer, a snapshot of live model failures appended as they are found, or a hand-curated named corpus assembled from known failure patterns.

## Decision Drivers

* CI must run entirely offline — no live LLM calls, no random input generation that could introduce flakiness.
* Each failure case must be reproducible, named, and attributable to a specific failure domain (e.g. `json_extraction`, `react_loop`, `provider_usage`).
* The corpus must be deterministic: the same inputs produce the same outputs on every run.
* New failure modes discovered in production or during development should be promotable to the corpus with a concrete, named case.
* The suite must cover multiple layers: engine utilities (`extract_json`), pattern-level behaviour (`structured`, `refine_loop`, `react_loop`), and provider-level validation (`LLMResponse` token bounds).

## Considered Options

* Option A: Hand-curated named `EvalCase` corpus (`FAILURE_CORPUS` list in `tests/eval_failure_cases.py`)
* Option B: Property-based tests using Hypothesis to generate malformed inputs
* Option C: Snapshot-based tests that record live model responses and replay them

## Decision Outcome

**Chosen option:** Option A (hand-curated named corpus), as implemented in `tests/eval_failure_cases.py`. The file defines 13 named cases (`FC-01` through `FC-13`) across five domains, each as a pair of `async def run()` and `def check(output)` functions wrapped in an `EvalCase` dataclass. Cases are assembled into a `FAILURE_CORPUS` list consumed by `tests/test_eval_failure_corpus.py` via `run_eval_suite()`.

Each case has a `metadata` dict with a `"domain"` key (`json_extraction`, `structured`, `refine_loop`, `react_loop`, `provider_usage`) for filtering and reporting. The `MockProvider` is used throughout to supply deterministic responses without any network calls.

Coverage of the corpus:

| Range | Domain | What is tested |
|-------|--------|----------------|
| FC-01 to FC-04 | `json_extraction` | Trailing comma, unterminated object, prose wrapper (pass), bare integer root |
| FC-05 to FC-06 | `structured` | All repair attempts exhausted; validator blocks first response, repair succeeds |
| FC-07 | `refine_loop` | Prompt-injection payload in candidate text must not inflate the judge's score |
| FC-08 to FC-10 | `react_loop` | String arg where integer expected is blocked; bool arg blocked; oversized observation truncated |
| FC-11 to FC-13 | `provider_usage` | Negative token count raises `ProviderError`; absurdly large count raises; boolean count rejected |

### Positive Consequences

* Every case is named, reproducible, and fully offline — no flakiness.
* Failure modes are explicitly documented in code; a reader can see exactly which edge case each case covers.
* New cases discovered in production can be added with a specific name and `domain` tag, making the corpus grow incrementally.
* `run_eval_suite()` reports `passed`, `failed_count`, and `accuracy` — the CI gate requires 100% pass on the deterministic corpus.

### Negative Consequences

* The corpus only covers failure modes the authors have anticipated or encountered; unknown failure modes are not covered until a case is added.
* Hand-curation requires discipline: cases must be added when new failure modes are found, not deferred.

## Pros and Cons of the Options

### Option A: Hand-curated named corpus

* **Good:** Deterministic, fully offline, no flakiness.
* **Good:** Each case is named and documents a specific real failure mode.
* **Good:** Incrementally growable: add a case when a new failure mode is found.
* **Bad:** Does not discover unknown failure modes automatically.

### Option B: Property-based tests (Hypothesis)

* **Good:** Can discover unexpected edge cases automatically.
* **Bad:** Adds `hypothesis` as a dev dependency.
* **Bad:** Random input generation may not reliably reproduce the specific JSON shapes that real LLMs produce (e.g. trailing-comma objects are a known model behaviour, not a random input).
* **Bad:** Non-deterministic shrinking can make failures harder to reproduce.

### Option C: Snapshot-based replay

* **Good:** Uses real model outputs.
* **Bad:** Requires live API calls to build the snapshot library, coupling the corpus to a specific provider and model version.
* **Bad:** Model output format changes can silently invalidate snapshots.
* **Bad:** Does not run offline without a pre-existing snapshot store.
