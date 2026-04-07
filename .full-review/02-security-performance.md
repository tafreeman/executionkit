# Phase 2: Security & Performance Review

## Security Findings

**Totals:** Critical: 1, High: 4, Medium: 6, Low: 5

### Critical (1)

- **SEC-C1: Prompt Injection in Default Evaluator (CWE-74)** -- `refine_loop.py:119-146`. The default evaluator interpolates LLM-generated content into a scoring prompt using XML delimiters. An adversarial response can escape the delimiters (`</response_to_rate>`) and manipulate evaluation scores, undermining the quality-convergence mechanism. The XML-delimiter approach is the weakest prompt injection defense; LLMs do not reliably enforce tag boundaries. Fix: use structured output mode, separate system/user messages, randomized unguessable delimiters, and document that production deployments should supply custom evaluators.

### High (4)

- **SEC-H1: Shallow Immutability Enables Tool-Call Injection (CWE-471)** -- `provider.py`, `types.py`. `LLMResponse` and `Tool` are `frozen=True` but contain mutable fields (`list[ToolCall]`, `dict[str, Any]`). Post-parse mutation can inject/modify tool calls. Fix: convert to `tuple` and `MappingProxyType`.
- **SEC-H2: Broad Exception Catch Swallows Security-Relevant Errors (CWE-755)** -- `provider.py:311-316`. Bare `except Exception` discards error response bodies that may contain security-relevant info (key revocation, account suspension). Fix: narrow to `(json.JSONDecodeError, ValueError, UnicodeDecodeError)`.
- **SEC-H3: Tool Execution Has No Resource Limits Beyond Timeout (CWE-400)** -- `react_loop.py:269-283`. Tool functions can allocate unbounded memory, spawn subprocesses, perform SSRF. No sandboxing, memory limits, or network isolation. Fix: document as security boundary; consider `max_result_bytes` and `tool_error_handler` callback.
- **SEC-H4: Error Messages Leak Provider Response Details (CWE-209)** -- `provider.py:496-510`. `_redact_sensitive` regex has gaps: misses non-standard key prefixes, JSON-embedded keys, short tokens. Fix: more aggressive redaction; option to suppress provider details in production.

### Medium (6)

- **SEC-M1:** No TLS certificate configuration; `http://` URLs accepted without warning.
- **SEC-M2:** `kwargs` passthrough in `complete()` enables payload injection (model/messages/temperature override).
- **SEC-M3:** Budget enforcement TOCTOU window under concurrency; budget exceeded by up to `max_concurrency - 1` calls.
- **SEC-M4:** Tool argument validation is shallow (top-level types only); nested/string/numeric constraints ignored.
- **SEC-M5:** `SECURITY.md` contains inaccurate `__repr__` guidance; missing `dataclasses.asdict()` exposure warning.
- **SEC-M6:** No input size limits on prompts; large strings can cause OOM or timeout.

### Low (5)

- **SEC-L1:** Debug logging with `exc_info=True` may leak sensitive tool data.
- **SEC-L2:** `retry_after` header parsed without upper bound (server can force infinite sleep).
- **SEC-L3:** No `py.typed` marker reduces downstream type safety.
- **SEC-L4:** Placeholder GitHub URLs in `pyproject.toml` could be squatted.
- **SEC-L5:** Dev dependencies lack upper version pins.

### Positive Security Findings

Zero runtime dependencies (excellent supply chain posture), API key masking in `__repr__`, credential redaction in error messages, tool argument validation, tool timeout enforcement, observation truncation, budget enforcement, bandit + ruff S rules integration, frozen dataclasses, evaluator prompt injection awareness, `SECURITY.md` with reporting SLAs.

---

## Performance Findings

**Totals:** Critical: 1, High: 4, Medium: 6, Low: 5

### Critical (1)

- **P-C1: CostTracker TOCTOU Race Under Concurrent Budget Checks** -- `base.py:65-97`, `cost.py:17-65`. The call-count TOCTOU was partially mitigated (pre-increment), but token budget checks have no reservation mechanism. Under `consensus(num_samples=5)`, 5 concurrent calls can all pass the token budget check simultaneously, allowing up to 5x the intended token spend before enforcement triggers. Fix: implement token reservation, enforce budget at pattern level, or document as approximate.

### High (4)

- **P-H1: urllib Fallback Blocks Event Loop Thread Pool** -- `provider.py:329-372`. Without httpx, stdlib `urllib` uses `asyncio.to_thread` with a limited thread pool and no connection pooling. Concurrent patterns degrade to near-serial execution. 5-sample consensus: ~2s with httpx vs ~10s+ with urllib. Fix: make httpx required or document urllib as minimal-only.
- **P-H2: Unbounded Message History Growth in react_loop** -- `react_loop.py:156-226`. Messages grow by 2+ entries/round with full tool observations. 8 rounds x 3 tools x 12KB = ~288KB of observation text. Token cost grows quadratically since entire history is sent each round. `max_history_messages` defaults to None (disabled). Fix: set sensible default; implement smarter trimming.
- **P-H3: Retry Delay Ignores Provider Retry-After Header** -- `engine/retry.py:40-50`. `with_retry` always uses jittered exponential backoff, ignoring `RateLimitError.retry_after`. Client retries too soon, wastes retry attempts, converts temporary 429s into permanent failures. Fix: use `max(config.get_delay(attempt), exc.retry_after)`.
- **P-H4: httpx AsyncClient Created Once, Never Recycled** -- `provider.py:219-245`. No connection pool limits configured; stale connections in long-lived processes; connection-level errors (`httpx.ConnectError`, `httpx.TimeoutException`) not retried. Fix: accept pool config parameters; add connection errors to retryable set.

### Medium (6)

- **P-M1:** Consensus stores all response strings + raw API payloads simultaneously (linear memory scaling with `num_samples`).
- **P-M2:** `gather_strict` creates all tasks eagerly before semaphore throttling (O(N) overhead regardless of concurrency limit).
- **P-M3:** `pipe()` accumulates all step metadata indefinitely; copies `MappingProxyType` back to mutable `dict` per step.
- **P-M4:** Semaphore created per-call, not shared across patterns. No global concurrency limit; N concurrent consensus calls allow N x `max_concurrency` simultaneous API calls.
- **P-M5:** Default evaluator makes 1 extra LLM call per `refine_loop` iteration (~50% more calls than expected). Budget consumed by evaluation not clearly communicated.
- **P-M6:** `json.dumps` called on tool arguments that were just parsed from JSON; redundant round-trip serialization.

### Low (5)

- **P-L1:** `ConvergenceDetector._scores` grows unbounded (only last 2 needed).
- **P-L2:** `_trim_messages` creates new list every round even when no trimming needed.
- **P-L3:** `MappingProxyType` wrapping on every `PatternResult` construction (minor allocation overhead).
- **P-L4:** `inspect.signature` called per step in `pipe()` (uncached reflection).
- **P-L5:** No separate connection vs. read timeout; single 120s timeout conflates both phases.

---

## Critical Issues for Phase 3 Context

### Testing Requirements (from Security)

1. **SEC-C1 (Prompt injection):** Tests should verify evaluator behavior with adversarial inputs containing delimiter-escape sequences. Coverage of the `refine_loop` default evaluator path is critical.
2. **SEC-H1 (Shallow immutability):** Tests should verify that `LLMResponse.tool_calls` and `Tool.parameters` cannot be mutated after construction.
3. **SEC-M3 / P-C1 (Budget TOCTOU):** Concurrent budget enforcement needs integration tests with multiple simultaneous `checked_complete` calls to verify call-count and token budget integrity.
4. **SEC-M4 (Tool validation):** Tests should cover nested object validation, string constraints, and null handling to document current validation boundaries.

### Testing Requirements (from Performance)

5. **P-H2 (Message history growth):** Tests should verify `max_history_messages` trimming behavior and measure token cost across rounds.
6. **P-H3 (Retry-After ignored):** Tests should verify retry timing respects the `retry_after` value from `RateLimitError`.
7. **P-M4 (Per-call semaphore):** Integration tests should verify aggregate concurrency behavior when multiple patterns run in parallel.

### Documentation Requirements

8. **SEC-M5:** `SECURITY.md` contains inaccurate `__repr__` guidance that must be corrected. Missing warnings about `dataclasses.asdict()` and stack trace exposure of API keys.
9. **SEC-H3 / SEC-M2:** Tool execution security boundary and `kwargs` passthrough risks need prominent documentation.
10. **P-H1:** urllib fallback limitations need documentation (not suitable for concurrent patterns).
11. **P-M5:** Default evaluator LLM call overhead should be documented in `refine_loop` docstring.
12. **P-C1:** Token budget approximation under concurrency should be documented if not fixed.

### Cross-Cutting Concerns

- **SEC-M3 and P-C1 are the same underlying issue** (CostTracker TOCTOU race) identified independently by both reviewers. The security review focused on call-count bypass; the performance review extended it to the more severe token-budget bypass. This validates it as a high-priority fix.
- **SEC-C1 and P-M5 overlap** on the default evaluator in `refine_loop`. Security sees prompt injection risk; performance sees unexpected LLM call overhead. Both recommend custom evaluator guidance.
- **SEC-H3 and P-H1 overlap** on tool execution boundaries. Security sees sandboxing gaps; performance sees resource exhaustion under the urllib fallback. Both recommend documentation at minimum.
