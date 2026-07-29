# Architecture decision records

Each record explains a decision that affects a stable package boundary. A
record describes the context, the decision, its consequences, and the main
alternative not chosen.

| Record | Decision | Status | Date |
|---|---|---|---|
| [ADR-001](001-structural-protocols.md) | Use structural provider protocols. | Accepted | 2026-05-11 |
| [ADR-002](002-flat-layout.md) | Keep the package at the repository root. | Accepted | 2026-05-11 |
| [ADR-003](003-single-provider.md) | Use one OpenAI-compatible provider. | Accepted | 2026-05-11 |
| [ADR-004](004-zero-runtime-dependencies.md) | Keep the base install dependency-free. | Accepted | 2026-05-11 |
| [ADR-005](005-caller-supplied-cost-rates.md) | Require callers to supply price rates. | Accepted | 2026-05-22 |
| [ADR-006](006-eval-failure-corpus.md) | Maintain a named failure-case corpus. | Accepted | 2026-06-08 |
| [ADR-007](007-async-first-sync-wrappers.md) | Make pattern APIs async-first. | Accepted | 2026-05-22 |
| [ADR-008](008-workflow-checkpoint-resume.md) | Let callers persist workflow checkpoints. | Accepted | 2026-06-18 |
| [ADR-009](009-approval-gate-timeout-policy.md) | Make approval timeout behavior explicit. | Accepted | 2026-06-18 |
| [ADR-010](010-optional-otel-span-emission.md) | Probe once for optional OpenTelemetry support. | Accepted | 2026-06-18 |
| [ADR-011](011-map-reduce-pattern.md) | Use a strict concurrent map phase and one reduce call. | Accepted | 2026-06-18 |
| [ADR-012](012-stdlib-mcp-server.md) | Ship a small stdio MCP server. | Accepted | 2026-07-02 |
| [ADR-013](013-claude-in-ci-eval.md) | Keep model-judged corpus review advisory. | Accepted | 2026-07-02 |
| [ADR-014](014-message-batches.md) | Keep Anthropic batches separate from live patterns. | Accepted | 2026-07-03 |
| [ADR-015](015-react-loop-tool-sandbox.md) | Enforce a bounded tool-execution contract. | Accepted | 2026-07-03 |

New records use the next number and the same four-section structure. Do not
rewrite an old decision to hide a replacement. Mark it superseded and link to
the new record.
