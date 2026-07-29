# ADR-007: Make pattern APIs async-first

- Status: Accepted
- Date: 2026-05-22
- Updated: 2026-07-28

## Context

Provider calls, retries, streaming, concurrent sampling, and tool execution are
I/O-bound operations built on `asyncio`.

## Decision

Implement patterns as async functions. Provide thin synchronous wrappers for:

- `consensus`;
- `refine_loop`;
- `react_loop`;
- `structured`;
- `map_reduce`; and
- `pipe`.

The wrappers call `asyncio.run()` and reject use from an already running event
loop.

## Consequences

- The primary API composes with async applications without threads.
- Synchronous scripts have a direct entry point.
- Notebook and async-framework users must call the async functions with
  `await`.
- The sync wrappers must remain behaviorally aligned with the async functions.

## Rejected alternatives

A sync-first implementation would need internal threads or duplicated async
variants and would make cancellation and streaming harder to reason about.
