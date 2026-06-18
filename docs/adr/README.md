# Architecture Decision Records

Formal records of significant design decisions made during ExecutionKit's development.
Records follow the [MADR template](https://adr.github.io/madr/).

## Records

| ADR | Decision | Status | Date |
|-----|----------|--------|------|
| [ADR-001](001-structural-protocols.md) | Structural protocols over ABC | Accepted | 2026-05-11 |
| [ADR-002](002-flat-layout.md) | Flat package layout over src/ | Accepted | 2026-05-11 |
| [ADR-003](003-single-provider.md) | Single OpenAI-compatible Provider over adapter matrix | Accepted | 2026-05-11 |
| [ADR-004](004-zero-runtime-dependencies.md) | Zero runtime dependencies; httpx as optional extra | Accepted | 2026-05-11 |
| [ADR-005](005-caller-supplied-cost-rates.md) | Caller-supplied cost rates over built-in price table | Accepted | 2026-05-22 |
| [ADR-006](006-eval-failure-corpus.md) | Curated failure-corpus eval methodology | Accepted | 2026-06-08 |
| [ADR-007](007-async-first-sync-wrappers.md) | Async-first design with sync wrappers | Accepted | 2026-05-22 |
| [ADR-008](008-workflow-checkpoint-resume.md) | Caller-supplied checkpoint function for workflow resume | Accepted | 2026-06-18 |
| [ADR-009](009-approval-gate-timeout-policy.md) | Three-option timeout policy for ApprovalGate | Accepted | 2026-06-18 |
| [ADR-010](010-optional-otel-span-emission.md) | importlib probe for optional OpenTelemetry integration | Accepted | 2026-06-18 |
| [ADR-011](011-map-reduce-pattern.md) | gather_strict map phase with single reduce call | Accepted | 2026-06-18 |

## Format

Each ADR file is named `NNN-short-title.md` and follows the
[MADR template](https://adr.github.io/madr/). Status values:
**Proposed** -> **Accepted** / **Deprecated** / **Superseded**.
