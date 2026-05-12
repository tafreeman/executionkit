# Phase 2B: Performance Analysis

**Reviewer:** perf-analyst
**Date:** 2026-04-06
**Scope:** Memory management, concurrency, I/O bottlenecks, budget/token efficiency, retry behavior
**Source files reviewed:** `engine/parallel.py`, `engine/retry.py`, `engine/convergence.py`, `provider.py`, `patterns/consensus.py`, `patterns/react_loop.py`, `patterns/refine_loop.py`, `compose.py`, `cost.py`, `patterns/base.py`, `types.py`

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 1     |
| High     | 4     |
| Medium   | 6     |
| Low      | 5     |
| **Total** | **16** |

---

## Critical

### P-C1: CostTracker TOCTOU race under concurrent budget checks

**File:** `patterns/base.py:65-97`, `cost.py:17-65`
**Category:** Concurrency

`checked_complete` performs a read-then-write on `CostTracker._calls`: it reads the current count at line 67, compares against the budget, then increments at line 87. When multiple coroutines share the same `CostTracker` (as in `consensus` which fires `num_samples` concurrent calls through `gather_strict` -> `checked_complete`), multiple coroutines can pass the budget check simultaneously before any of them increment the counter.

The code comment at line 85 acknowledges this ("P0-3: TOCTOU fix") and pre-increments `_calls` before the await. However, the *token budget checks* at lines 73-84 (`input_tokens`, `output_tokens`) have **no such reservation** — they read `current = tracker.to_usage()` and compare, but tokens are only recorded *after* the HTTP call returns. Under concurrent execution, N coroutines can all pass the token budget check before any of them records tokens, allowing the budget to be exceeded by up to N-1 times the per-call token cost.

**Impact:** With `consensus(num_samples=5)`, up to 5 concurrent calls can all pass the budget check simultaneously. For expensive models this could mean 5x the intended token spend before any budget enforcement triggers.

**Fix:** Either (a) implement token reservation similar to the call-count reservation (estimate tokens from message size), (b) enforce budget at the pattern level by checking cumulative cost between iterations rather than relying on per-call checks in concurrent contexts, or (c) document that token budgets are approximate under concurrency and only call-count budgets are precise.

---

## High

### P-H1: urllib fallback blocks the event loop thread pool

**File:** `provider.py:329-372`
**Category:** I/O bottleneck

When `httpx` is not installed, `_post_urllib` uses `asyncio.to_thread(_sync)` to run blocking stdlib HTTP in a thread. The default `asyncio` thread pool executor has a limited size (typically `min(32, os.cpu_count() + 4)`). Under concurrent workloads like `consensus(num_samples=10)` or multiple `pipe()` steps running in parallel, these threads can be exhausted, causing all subsequent `to_thread` calls to queue and wait — effectively serializing what should be concurrent I/O.

Additionally, `urllib.request` creates a new TCP connection per request with no connection pooling. Every LLM call pays the full TCP + TLS handshake cost (~100-300ms to typical cloud endpoints), which accumulates significantly in patterns like `consensus` that make many calls.

**Impact:** With the urllib fallback, concurrent patterns degrade to near-serial execution under load. A 5-sample consensus that takes ~2s with httpx connection pooling could take ~10s+ with urllib due to serialized connections and handshake overhead.

**Fix:** (a) Make `httpx` a hard dependency rather than optional (it's listed in pyproject.toml already), or (b) configure a larger `ThreadPoolExecutor` when using the urllib fallback, or (c) document that the urllib fallback is for minimal environments only and is not suitable for concurrent patterns.

### P-H2: Unbounded message history growth in react_loop

**File:** `patterns/react_loop.py:156-226`
**Category:** Memory management

The `messages` list in `react_loop` grows by 2+ entries per round (1 assistant message + 1 tool result per tool call). With `max_rounds=8` and an LLM that calls multiple tools per round, the message list can grow to 50+ entries, each containing full tool observation strings up to `max_observation_chars=12000` characters.

Worst case: 8 rounds x 3 tool calls/round x 12,000 chars = ~288KB of observation text alone, plus all assistant messages and the growing conversation context. Each round sends the *entire* accumulated history to the LLM, so the token cost grows quadratically: round N sends ~N times the per-round content.

The `max_history_messages` parameter exists as a mitigation but defaults to `None` (disabled). The `_trim_messages` function helps when enabled, but it always preserves the first message and the most recent entries — it can discard intermediate tool results that contained context the LLM was relying on, leading to degraded response quality.

**Impact:** Quadratic token cost growth; potential memory pressure on the client side; possible context window overflow on the provider side (resulting in truncated or failed requests).

**Fix:** (a) Set a sensible default for `max_history_messages` (e.g., 20), (b) implement a smarter trimming strategy that summarizes discarded tool results rather than silently dropping them, or (c) track cumulative message size and warn/trim when approaching known context limits.

### P-H3: Retry delay ignores provider Retry-After header

**File:** `engine/retry.py:40-50`, `provider.py:317-324`
**Category:** Retry behavior

`RateLimitError` captures the `retry_after` value from the HTTP 429 response header, but `with_retry` at line 88 always uses `config.get_delay(attempt)` — the jittered exponential backoff — ignoring the `retry_after` attribute on the caught exception entirely. When a rate-limited API says "retry after 30 seconds", the retry logic might wait only 0.5s (jittered from a 1s base), immediately hitting the rate limit again and wasting another API call.

This creates a pathological loop: the client retries too soon, gets 429 again, retries too soon again, until `max_retries` is exhausted. Each wasted retry consumes a retry slot and delays the eventual success.

**Impact:** Rate-limited requests waste retry attempts and take longer to succeed. Under sustained rate limiting, the pattern exhausts retries without ever waiting long enough, converting a temporary condition into a permanent failure.

**Fix:** In `with_retry`, check if the caught exception is a `RateLimitError` and use `max(config.get_delay(attempt), exc.retry_after)` as the sleep duration.

### P-H4: httpx AsyncClient created once, never recycled

**File:** `provider.py:219-229, 238-245`
**Category:** Connection management

`Provider.__post_init__` creates a single `httpx.AsyncClient` at construction time. This client is stored for the lifetime of the `Provider` instance. There are several issues:

1. **No connection pool limits configured:** The default `httpx.AsyncClient` uses a pool of 100 connections with 20 max keepalive connections. For high-concurrency patterns like `consensus(num_samples=20, max_concurrency=20)`, all 20 requests go to the same host — the connection pool may bottleneck or create excessive connections.

2. **Stale connections:** Long-lived providers (e.g., in a web server context) may hold stale TCP connections that have been closed server-side, causing failed requests on the first attempt after idle periods.

3. **No retry on connection errors:** The retry config only handles `RateLimitError` and `ProviderError` (HTTP-level errors). Connection-level failures (DNS resolution, TCP connect timeout, TLS errors) from `httpx` raise `httpx.ConnectError` or `httpx.TimeoutException`, which are not in the `retryable` tuple and immediately propagate as unhandled exceptions.

**Impact:** Under high concurrency the connection pool is untuned; under long-lived usage connections may go stale; transient network errors are not retried.

**Fix:** (a) Accept `httpx` pool configuration parameters (`max_connections`, `max_keepalive_connections`), (b) add `httpx.ConnectError` and `httpx.TimeoutException` to the default retryable exceptions (or wrap them as `ProviderError`), (c) document expected lifecycle (short-lived vs. long-lived).

---

## Medium

### P-M1: consensus stores all response strings in memory simultaneously

**File:** `patterns/consensus.py:84-88`
**Category:** Memory management

After `gather_strict` completes, `consensus` holds `responses` (list of `LLMResponse` objects including `raw` API payloads), `contents` (extracted strings), and `normalized` (whitespace-collapsed copies) all in memory simultaneously. For `num_samples=10` with `max_tokens=4096`, this could be ~120KB of text strings plus ~10 full raw API response dicts.

This is generally acceptable for typical usage, but the `LLMResponse.raw` field stores the *entire* API response JSON (including the full response text again). With `num_samples=20`, peak memory could reach several MB of duplicated response data.

**Impact:** Moderate memory overhead that scales linearly with `num_samples`. Not critical for typical usage (5-10 samples) but could matter in memory-constrained environments or with very large responses.

**Fix:** (a) Clear `raw` references after extracting content, or (b) make `raw` storage opt-in via a parameter, or (c) accept as reasonable for the expected scale.

### P-M2: gather_strict creates all tasks before any execution begins

**File:** `engine/parallel.py:60-76`
**Category:** Concurrency

`gather_strict` creates all tasks upfront in the `TaskGroup` loop (line 69-70), then the semaphore throttles actual execution. This means if `coros` has 100 items with `max_concurrency=10`, all 100 `asyncio.Task` objects are created immediately (each consuming ~1KB+ of memory for the task frame), even though only 10 can execute at a time.

For typical usage (consensus with 5-10 samples), this is negligible. But `gather_strict` is a general-purpose utility that could be called with larger lists.

**Impact:** O(N) task creation overhead regardless of concurrency limit. Negligible for N < 100, measurable for N > 1000.

**Fix:** (a) Use an async iterator pattern that creates tasks lazily as semaphore slots become available, or (b) document the eager-creation behavior and recommend small batch sizes.

### P-M3: pipe() accumulates all step metadata in memory

**File:** `compose.py:109-133`
**Category:** Memory management

`pipe()` appends `dict(result.metadata)` for every step into `step_metadata` (line 127), and the final result includes the entire chain's metadata history. For deep pipelines, this creates a nested structure where each step's metadata (which may include `score_history`, `tool_calls_made`, etc.) is preserved indefinitely.

Additionally, each step converts `result.metadata` (a `MappingProxyType`) back to a mutable `dict` via `dict(result.metadata)` — creating a copy. For patterns that store large metadata (e.g., `score_history` in `refine_loop`), this duplication is unnecessary.

**Impact:** Linear memory growth with pipeline depth. Metadata from early steps remains reachable for the lifetime of the final result.

**Fix:** (a) Make metadata accumulation opt-in, (b) only store metadata from the final step by default, or (c) accept as a design choice for debuggability.

### P-M4: Semaphore created per-call, not shared across patterns

**File:** `engine/parallel.py:28, 60`
**Category:** Concurrency

Both `gather_resilient` and `gather_strict` create a new `asyncio.Semaphore` per invocation. If a user calls `consensus()` multiple times concurrently (e.g., in a `pipe()` with parallel steps), each consensus creates its own semaphore with `max_concurrency=5`, allowing 5 * N concurrent LLM calls where N is the number of concurrent consensus invocations.

There is no global concurrency limit across the application, so a pipeline of 3 concurrent consensus steps with `max_concurrency=5` each would fire 15 simultaneous API calls, potentially overwhelming the provider's rate limit.

**Impact:** No protection against aggregate concurrency across pattern invocations. Can lead to unexpected rate limiting and cascading retries.

**Fix:** (a) Accept an optional shared `asyncio.Semaphore` parameter in `gather_strict`/`gather_resilient` and propagate from pattern-level configuration, or (b) implement a global concurrency limiter at the `Provider` level.

### P-M5: Default evaluator in refine_loop makes an LLM call per iteration

**File:** `patterns/refine_loop.py:119-148`
**Category:** Token/budget efficiency

When no custom evaluator is provided, `refine_loop` uses a default LLM-based evaluator that makes one additional LLM call per iteration (at `max_tokens=16`, `temperature=0.1`). With `max_iterations=5`, this means up to 5 extra LLM calls just for scoring, plus the 1 initial + 5 refinement calls = 11 total LLM calls for a single `refine_loop` invocation.

The evaluator cost shares the same `tracker` and `max_cost` budget (noted in Phase 1 as CQ-M4/AR-M4). Users may not realize that their token budget is being consumed by evaluation calls in addition to generation calls.

**Impact:** ~50% more LLM calls than expected if users are unaware of evaluator overhead. Budget can be exhausted sooner than anticipated.

**Fix:** (a) Document the evaluator overhead prominently in the docstring, (b) add separate budget tracking for evaluator vs. generation calls in metadata, (c) consider a lightweight non-LLM default evaluator option.

### P-M6: json.dumps called on tool arguments for every tool call message

**File:** `patterns/react_loop.py:197`
**Category:** Minor CPU overhead

Each tool call's arguments are serialized via `json.dumps(tc.arguments)` when building the assistant message (line 197). These arguments were already parsed from JSON in `_parse_tool_arguments` (provider.py:452-467). The round-trip JSON parse -> dict -> JSON serialize is redundant; the original JSON string could be preserved.

**Impact:** Negligible for typical usage. Could matter in tight loops with many tool calls and large argument payloads.

**Fix:** (a) Preserve the raw JSON string in `ToolCall` alongside the parsed dict, or (b) accept the overhead as minimal.

---

## Low

### P-L1: ConvergenceDetector._scores list grows unbounded

**File:** `engine/convergence.py:46`
**Category:** Memory management

`ConvergenceDetector._scores` appends every score forever. Only the last two scores are ever used for delta computation (line 54). For a `refine_loop` with `max_iterations=5` this stores at most 6 floats (48 bytes) — negligible. However, if `ConvergenceDetector` is reused across multiple loops without calling `reset()`, the list grows indefinitely.

**Impact:** Negligible for intended usage. Only relevant if the detector is reused improperly.

**Fix:** Only store the last 2 scores, or document that `reset()` must be called between uses.

### P-L2: _trim_messages creates a new list on every round even when no trimming needed

**File:** `patterns/react_loop.py:73-83`
**Category:** Minor allocation overhead

When `len(messages) <= max_messages`, `_trim_messages` returns the original list (no copy). However, when trimming *is* needed, it creates a new list via `[messages[0], *messages[-(max_messages - 1):]]` which involves slicing and list construction. This is called on every round of `react_loop`.

**Impact:** Negligible. List construction of ~20 items is sub-microsecond.

### P-L3: MappingProxyType wrapping on every PatternResult construction

**File:** `types.py:58-59`, `consensus.py:113`, `refine_loop.py:209`, `react_loop.py:184`
**Category:** Minor allocation overhead

Every `PatternResult` wraps its metadata in `MappingProxyType({})`. This is the correct immutability approach but adds one extra object allocation per result. The default factory `lambda: MappingProxyType({})` creates a new empty proxy for results that don't have metadata.

**Impact:** Negligible. `MappingProxyType` is a thin wrapper with minimal overhead.

### P-L4: inspect.signature called per step in pipe()

**File:** `compose.py:54-70`
**Category:** Minor CPU overhead

`_filter_kwargs` calls `inspect.signature(step)` for every step in the pipeline. `inspect.signature` is not cached by default and involves reflection. For short pipelines (2-3 steps) this is negligible. For longer pipelines or frequently-called pipes, the reflection cost could add up.

**Impact:** Negligible for typical usage (2-5 steps). Python 3.11+ caches signatures internally, further reducing concern.

### P-L5: No connection timeout separate from request timeout

**File:** `provider.py:209, 224`
**Category:** I/O configuration

`Provider.timeout` is used as both the connection timeout and the read timeout (passed directly to `httpx.AsyncClient(timeout=self.timeout)`). A single 120s timeout means a connection that takes 60s to establish still has 60s left for the response. However, LLM completions can legitimately take 30-60s for large outputs, while connection establishment should fail fast (5-10s). Conflating the two means either connections hang too long or legitimate slow responses timeout.

**Impact:** Suboptimal timeout behavior at the edges. Users must choose a single timeout value that works for both connection and response phases.

**Fix:** Accept separate `connect_timeout` and `read_timeout` parameters, defaulting to e.g., 10s and 120s respectively.

---

## Phase 1 Cross-Reference

Several Phase 1 findings have direct performance implications confirmed by this analysis:

| Phase 1 ID | Performance Impact | Confirmed/Extended |
|------------|-------------------|--------------------|
| CQ-H1 / AR-H1 (CostTracker encapsulation) | TOCTOU race in concurrent budget checks | **Extended to P-C1**: token budget race is more severe than the call-count race that was already mitigated |
| AR-M4 (consensus lacks max_cost) | Unbounded cost in pipe() | **Confirmed**: consensus as a pipe step has no budget propagation |
| Phase 1 "No retry jitter" | Thundering herd | **Corrected**: RetryConfig.get_delay() *does* use full jitter (random.uniform). Phase 1 finding was inaccurate. However, **P-H3** identifies that the jittered delay ignores the Retry-After header, which is the actual problem. |
| AR-M5 (shallow immutability) | No direct performance issue for single-threaded async. Concurrent access is safe because asyncio is cooperative — no true parallelism on shared objects. | **Not a performance concern** for async code |

---

## Recommendations Priority

1. **P-C1** — Fix token budget TOCTOU race (Critical; cost control bypass under concurrency)
2. **P-H3** — Respect Retry-After header in retry logic (High; wastes retries, extends outage)
3. **P-H4** — Configure httpx pool limits and retry transient connection errors (High; production reliability)
4. **P-H1** — Address urllib fallback limitations or make httpx required (High; performance cliff)
5. **P-H2** — Set default max_history_messages in react_loop (High; quadratic cost growth)
6. **P-M4** — Add global/shared concurrency limiting (Medium; prevents rate limit storms)
7. **P-M5** — Document evaluator LLM call overhead (Medium; user expectation management)
