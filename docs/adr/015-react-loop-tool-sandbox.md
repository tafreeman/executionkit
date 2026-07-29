# ADR-015: Enforce a bounded tool-execution contract

- Status: Accepted
- Date: 2026-07-03
- Updated: 2026-07-25

## Context

In `react_loop()`, model output selects a registered tool and supplies its
arguments. The loop must limit malformed or excessive requests before calling
application code.

## Decision

Before execution, the loop:

1. rejects duplicate registered tool names;
2. limits tool calls per round;
3. requires a JSON object and validates the supported top-level schema subset;
4. fails closed on unsupported constraints when `jsonschema` is absent;
5. applies full validation when the optional `jsonschema` extra is present;
6. asks an `ApprovalGate` when configured;
7. applies a bounded timeout;
8. runs calls from the same round concurrently; and
9. truncates observations before returning them to the model.

Trace events redact tool arguments by default.

## Consequences

- Common malformed calls are rejected before application code runs.
- Optional full schema validation does not become a base dependency.
- Concurrency reduces latency but means same-round tools must not rely on call
  order.
- Registration-time duplicate checks prevent ambiguous dispatch.
- Tool code remains responsible for authorization, resource validation,
  idempotency, and side-effect control.

## Rejected alternatives

Executing calls without validation gives model output direct access to callable
arguments. Running every tool in a subprocess would not provide a complete
sandbox and would break normal in-process integrations.
