# ADR-007: Async-First Design with Sync Wrappers

**Date:** 2026-05-22
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** All four core patterns (`consensus`, `refine_loop`, `react_loop`, `structured`) were implemented as `async def` coroutines from the outset. Synchronous variants (`consensus_sync`, `refine_loop_sync`, `react_loop_sync`, `structured_sync`, `pipe_sync`) are thin wrappers in `executionkit/__init__.py` that call `asyncio.run()` on the underlying coroutine.

---

## Context and Problem Statement

ExecutionKit's patterns involve concurrent LLM calls (e.g. `consensus` fires `num_samples` requests in parallel via `asyncio.gather`), streaming retries, and tool execution loops (`react_loop`) that interleave network I/O with async Python function calls. The team needed to decide whether the primary public API should be synchronous (with an async variant for advanced users) or async-first (with sync wrappers for convenience).

Python's `asyncio` concurrency model imposes constraints: calling `asyncio.run()` from inside a running event loop raises `RuntimeError`. This means sync wrappers cannot be used inside Jupyter notebooks or other async frameworks without `nest_asyncio`, and must detect the running-loop condition explicitly.

## Decision Drivers

* `consensus` requires concurrent HTTP requests; `asyncio.gather` is the natural mechanism. Implementing this with threads adds complexity and the `GIL` limits true parallelism for CPU-bound code.
* `react_loop` tools are typed as `async def` callables — the pattern naturally `await`s them inside the loop.
* The library must be usable from plain synchronous scripts (the common case for quick experiments).
* Sync wrappers must fail clearly when called from inside an event loop, rather than hanging or producing `RuntimeError` stack traces that are hard to interpret.
* Coroutine objects must not be garbage-collected un-awaited (this emits a `"coroutine was never awaited"` `RuntimeWarning`).

## Considered Options

* Option A: Async-first (`async def` patterns); sync wrappers via `asyncio.run()` in `__init__.py`
* Option B: Sync-first; async variants via `asyncio.create_task()` or `loop.run_in_executor()`
* Option C: Threads for concurrency; no async API

## Decision Outcome

**Chosen option:** Option A (async-first with sync wrappers), as implemented across `executionkit/patterns/` and `executionkit/__init__.py`. Every pattern is an `async def` coroutine. Sync wrappers are defined in `__init__.py` using a shared `_run_sync()` helper that:

1. Calls `asyncio.get_running_loop()` to detect an active event loop.
2. If one is found, **closes the coroutine** before raising `RuntimeError("Cannot use sync wrappers inside an async context…")`. Closing the coroutine before raising prevents the `"coroutine was never awaited"` `RuntimeWarning` (verified by `test_run_sync_closes_coroutine_in_active_event_loop` in `tests/test_sync_wrappers.py`).
3. If no loop is running, calls `asyncio.run(coro)`.

The sync wrappers are exported from `__all__` alongside their async counterparts:

| Async | Sync |
|-------|------|
| `consensus` | `consensus_sync` |
| `refine_loop` | `refine_loop_sync` |
| `react_loop` | `react_loop_sync` |
| `structured` | `structured_sync` |
| `pipe` | `pipe_sync` |

### Positive Consequences

* `consensus` achieves true concurrency over `num_samples` calls without threads.
* `react_loop` tools are `async def` callables — tool execution integrates naturally into the pattern without executor hops.
* Synchronous scripts call `consensus_sync(provider, prompt)` with no `asyncio` knowledge required.
* The clear error message in `_run_sync` ("Cannot use sync wrappers inside an async context — use `await` instead, or install `nest_asyncio`") guides users toward the correct fix.
* The coroutine-close guard eliminates a class of `RuntimeWarning` noise.

### Negative Consequences

* Sync wrappers cannot be used inside Jupyter notebooks or async web frameworks without `nest_asyncio`. Users in those environments must use `await`.
* `asyncio.run()` creates and tears down a new event loop per call, which is wasteful if sync wrappers are called in a tight loop. Users with high-volume synchronous use cases should refactor to an async entry point.

## Pros and Cons of the Options

### Option A: Async-first with sync wrappers

* **Good:** Natural fit for concurrent I/O patterns (`consensus` fan-out, `react_loop` tool awaiting).
* **Good:** Sync wrappers provide a low-friction entry point for scripts and notebooks (with `nest_asyncio`).
* **Good:** Tool implementations are `async def` — no executor overhead for async tools.
* **Bad:** Sync wrappers cannot be called inside a running event loop without `nest_asyncio`.

### Option B: Sync-first with async variants

* **Good:** Synchronous use is the default; no `asyncio` knowledge needed for simple cases.
* **Bad:** Concurrent `consensus` calls require thread pools or explicit `asyncio` bridge code.
* **Bad:** Tool implementations would need to be synchronous or wrapped in `run_in_executor`, adding complexity.

### Option C: Threads for concurrency

* **Good:** Works in synchronous contexts without `asyncio`.
* **Bad:** Thread-per-request model does not scale well for large `num_samples`.
* **Bad:** The GIL limits parallelism for CPU-bound work (though LLM calls are I/O-bound).
* **Bad:** Thread safety for `CostTracker` would require locking; the module docstring in `cost.py` explicitly documents that `CostTracker` is not thread-safe by design and relies on asyncio cooperative scheduling for its budget-check invariant.
