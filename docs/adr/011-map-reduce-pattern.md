# ADR-011: Use a strict concurrent map phase and one reduce call

- Status: Accepted
- Date: 2026-06-18

## Context

Map-reduce needs defined ordering, failure, concurrency, and accounting
behavior.

## Decision

Run one map call per input with bounded concurrency and strict gathering.
Preserve input order in the collected results. Start one reduce call only after
every map call succeeds.

Use one shared `CostTracker`, retry policy, trace callback, and `max_cost`
budget across both phases. Reject streaming because the reduce prompt needs all
complete map outputs.

## Consequences

- The reduce step never receives an unexplained partial set.
- One map failure stops the pattern and exposes partial accumulated usage.
- Input order is deterministic even when calls finish out of order.
- Large inputs still require caller-selected concurrency and token budgets.

## Rejected alternatives

Resilient partial reduction can be useful, but it requires an application
policy for missing items. Sequential mapping would be simpler but would discard
safe I/O concurrency.
