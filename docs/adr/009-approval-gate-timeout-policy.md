# ADR-009: Make approval timeout behavior explicit

- Status: Accepted
- Date: 2026-06-18

## Context

An approval callback can block indefinitely. Different applications need to
stop, deny, or continue when a deadline expires.

## Decision

`ApprovalGate` accepts an optional timeout and one of three policies:

- `"raise"` raises `ApprovalTimeoutError` and is the default;
- `"deny"` returns a denied decision; and
- `"approve"` returns an approved decision and emits a warning at
  construction.

Async callbacks run directly. Synchronous callbacks run in a worker thread so
they do not block the event loop and can be bounded with `asyncio.wait_for()`.

## Consequences

- The safe default does not authorize work after an absent response.
- Applications can choose an availability policy explicitly.
- A timed-out synchronous thread may continue running even though its result is
  ignored.
- `"approve"` is fail-open and must be treated as a security decision.

## Rejected alternatives

A single hard-coded timeout result cannot fit both read-only and high-impact
operations. No timeout support would permit indefinite blocking.
