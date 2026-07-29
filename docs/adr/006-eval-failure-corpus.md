# ADR-006: Maintain a named failure-case corpus

- Status: Accepted
- Date: 2026-06-08

## Context

Model output can be malformed, truncated, adversarial, or inconsistent with a
tool schema. These failures need repeatable tests that do not call a live
provider.

## Decision

Keep a reviewed set of named `EvalCase` failures in
`tests/eval_failure_cases.py`. Run it with scripted providers in normal CI.
Each case states the input condition and the expected library behavior.

Add a case when a new production or review finding represents a distinct
failure mode. Keep general unit tests beside it; the corpus does not replace
unit or property-based testing.

## Consequences

- CI results are deterministic and failures name the behavior that regressed.
- Corpus quality depends on review and continued additions.
- The corpus proves handling of known cases, not all possible model output.
- Live-provider and model-judged evaluations remain separate opt-in evidence.

## Rejected alternatives

Live replay alone is too variable for a required CI gate. Generated fuzz cases
can find parser defects but do not replace explicit expected behavior for
security and recovery cases.
