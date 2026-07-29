# ADR-013: Keep model-judged corpus review advisory

- Status: Accepted
- Date: 2026-07-02

## Context

Deterministic tests prove that code matches the committed expectations. They do
not independently assess whether those expectations describe sensible handling
of each failure case.

## Decision

Use `scripts/claude_ci_eval.py` as a separate, opt-in review tier. It invokes
the Claude Code CLI in headless mode with a constrained verdict schema. The
workflow runs on its schedule or when explicitly labeled and remains
non-blocking.

Missing credentials or a missing CLI produce a clear skip unless the script is
run in its explicit gated mode. Deterministic corpus tests remain the required
CI authority.

## Consequences

- A second system can flag questionable corpus expectations.
- Results can vary as the model or service changes and must not be treated as a
  proof of correctness.
- The tier requires external credentials, a CLI install, and network access.
- A failing advisory result needs human review before changing an expectation.

## Rejected alternatives

Making model judgment merge-blocking would put a variable external decision in
the required build. Folding it into live provider tests would mix two different
questions: runtime behavior and corpus-quality review.
