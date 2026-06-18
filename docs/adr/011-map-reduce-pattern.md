# ADR-011: gather_strict Map Phase with Single Reduce Call

**Date:** 2026-06-18
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** Many pipeline use cases require applying an LLM prompt to each item in a collection and then combining the results. The team needed to design the map-reduce pattern's concurrency model, failure behaviour, and return type in a way that fits the existing `PatternResult[T]` contract.

---

## Context and Problem Statement

`map_reduce` processes a collection of string inputs through two phases: a map
phase that calls the provider once per input, and a reduce phase that combines
the results into a single answer. The design had to answer three questions.

First, how should the map phase handle partial failures? If three of ten map
calls fail, should the reduce phase proceed with seven results or should the
entire operation fail? Second, how should concurrency be bounded? Unbounded
parallelism can exhaust provider rate limits and memory. Third, what should the
return type be, and what metadata should the result carry?

## Decision Drivers

* Partial map failures produce semantically incomplete reduce input — a reduce
  over seven of ten summaries silently omits context, which is worse than an
  explicit error.
* Concurrency must be bounded by a caller-configurable limit to avoid rate
  limit errors on large input collections.
* The return type must satisfy `PatternResult[T]` so the pattern composes with
  `pipe()`, `Workflow`, and cost tracking without special-casing.
* The metadata should expose enough detail (map count, total calls) for
  callers to attribute cost without re-running the pattern.

## Considered Options

* Option A: `gather_strict` for the map phase (all-or-nothing), single reduce call
* Option B: `gather_resilient` for the map phase (tolerate partial failures), single reduce call
* Option C: Sequential map phase (no parallelism), single reduce call

## Decision Outcome

**Chosen option:** Option A (`gather_strict` map, single reduce call).

The map phase runs all coroutines concurrently via `gather_strict`, which
propagates the first exception and cancels remaining tasks. If any map call
fails, the entire `map_reduce` call raises immediately — no partial reduce is
attempted. Concurrency is bounded by `max_concurrency` (default 10), which
`gather_strict` enforces with a semaphore.

The reduce phase is always a single LLM call. Map outputs are joined with a
separator and substituted into `reduce_prompt_template` at the
`{mapped_outputs}` placeholder.

The function returns `PatternResult[str]` with `map_count`, `reduce_calls`,
and `total_calls` in metadata. Cost is accumulated across both phases via
`CostTracker`.

```python
result = await map_reduce(
    provider,
    inputs=["doc1", "doc2", "doc3"],
    map_prompt_template="Summarise this document: {item}",
    reduce_prompt_template="Combine these summaries: {mapped_outputs}",
    max_concurrency=5,
)
print(result.value)           # final combined answer
print(result.metadata["map_count"])  # 3
```

### Positive Consequences

* All-or-nothing semantics make failures explicit — callers never receive a
  silently incomplete reduce result.
* `gather_strict` with a semaphore bounds concurrency without requiring callers
  to partition inputs manually.
* `PatternResult[str]` integrates with `pipe()`, `Workflow`, and cost tracking
  without adaptation.
* `map_count` in metadata lets callers compute per-item cost from
  `result.cost` without re-running.

### Negative Consequences

* A single map failure aborts the entire batch. Callers that want partial
  results must filter inputs upfront or handle the exception and retry
  the failed subset.
* The reduce call always receives the full joined output. For very large
  input collections, the joined string may exceed the model's context window.
  Callers are responsible for chunking inputs to stay within limits.

## Pros and Cons of the Options

### Option A: gather_strict (all-or-nothing)

* **Good:** Failures are explicit and unambiguous — no silent partial results.
* **Good:** Semaphore-based concurrency bounding is built into `gather_strict`.
* **Bad:** One failure aborts the whole batch; no built-in retry for the
  failing subset.

### Option B: gather_resilient (tolerate partial failures)

* **Good:** Maximises the amount of output produced even when some inputs fail.
* **Bad:** The reduce prompt receives incomplete input with no indication of
  what was omitted — the model cannot distinguish a complete summary from a
  partial one.
* **Bad:** Callers cannot easily detect how many inputs were silently skipped
  without inspecting internal state.

### Option C: Sequential map phase

* **Good:** Simplest implementation; easiest to reason about.
* **Bad:** No parallelism — map phase latency scales linearly with input count,
  making large batches impractically slow.
* **Bad:** Contradicts the primary motivation for the pattern (fan-out
  parallelism over a collection).
