# ADR-009: Three-Option Timeout Policy for ApprovalGate

**Date:** 2026-06-18
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** Human-in-the-loop approval callbacks can block an async workflow indefinitely. The team needed a configurable timeout that works correctly for both async and blocking-sync callbacks.

---

## Context and Problem Statement

`ApprovalGate` wraps a callback that asks a human (or an automated system) to
approve an operation before it proceeds. In production, the callback might call
`input()`, write to a messaging queue, or send an HTTP request. Any of these
can block indefinitely if the human never responds or the external service is
unreachable.

Two distinct concerns arise. First, what should happen when the deadline
elapses — the caller's intent varies: some treat a timeout as a failure, others
want to proceed automatically (in headless pipelines), and others want to
default to safety by denying. Second, a synchronous callback like `input()`
completes before `asyncio.wait_for` is ever reached, silently defeating the
timeout if the callback is invoked inline on the event loop.

## Decision Drivers

* Async workflows must not block indefinitely waiting for a human response.
* The timeout behaviour must be caller-configurable — no single policy suits
  all use cases.
* Synchronous callbacks (including blocking I/O) must respect the timeout;
  calling them inline on the event loop defeats `asyncio.wait_for`.
* The implementation must introduce no new runtime dependencies.

## Considered Options

* Option A: Single `"raise"` policy — always raise `ApprovalTimeoutError` on timeout
* Option B: Three-option policy: `"raise"`, `"approve"`, `"deny"`
* Option C: No timeout support — callers wrap the gate themselves

## Decision Outcome

**Chosen option:** Option B (three-option policy via the `on_timeout` parameter).

`ApprovalGate.__init__` accepts `timeout_seconds: float | None` and
`on_timeout: Literal["approve", "deny", "raise"]` (default `"raise"`). When a
timeout fires, `_handle_timeout` maps the policy to an `ApprovalDecision` or
raises `ApprovalTimeoutError`.

To ensure synchronous callbacks respect the timeout, `_invoke` dispatches sync
callbacks to `asyncio.to_thread`. A synchronous callback invoked inline
completes before `asyncio.wait_for` has a chance to cancel it — running it in
a worker thread means the event loop stays free and `wait_for` can fire
normally.

```python
gate = ApprovalGate(
    callback=human_approval_callback,
    timeout_seconds=30.0,
    on_timeout="deny",  # safe default for automated pipelines
)
```

### Positive Consequences

* Callers choose the policy that fits their context: fail-safe (`"raise"`),
  auto-proceed (`"approve"`), or fail-closed (`"deny"`).
* `asyncio.to_thread` ensures blocking I/O callbacks (e.g., `input()`) do not
  starve the event loop and do respect the timeout deadline.
* The default (`"raise"`) preserves the original fail-fast behaviour so
  existing code that does not set a timeout is unaffected.

### Negative Consequences

* `asyncio.to_thread` requires Python 3.9+. This is acceptable — ExecutionKit
  already targets Python 3.11+.
* Running sync callbacks in a thread means they cannot access async resources
  directly. Callers with async approval workflows should provide an async
  callback instead.

## Pros and Cons of the Options

### Option A: Raise-only policy

* **Good:** Simple to implement and reason about.
* **Bad:** Headless pipelines with unattended approval gates must catch
  `ApprovalTimeoutError` and implement their own fallback — boilerplate the
  library should absorb.

### Option B: Three-option policy

* **Good:** Covers all three sensible timeout outcomes without requiring
  callers to catch and re-handle exceptions.
* **Good:** `asyncio.to_thread` correctly decouples sync callback completion
  from `wait_for` deadline tracking.
* **Bad:** Slightly more API surface than a raise-only approach.

### Option C: No timeout support

* **Good:** No additional API surface.
* **Bad:** Every caller that needs timeout behaviour must wrap `ApprovalGate`
  in their own `asyncio.wait_for` — and they will all independently encounter
  the sync-callback pitfall.
