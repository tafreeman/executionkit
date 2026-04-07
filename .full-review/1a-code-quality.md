# Code Quality Review — ExecutionKit

**Reviewer:** Code Quality Specialist (code-reviewer persona)
**Date:** 2026-04-06
**Scope:** All 15 source modules listed in review spec
**Baseline:** 324 tests, 83.29% coverage, Python 3.11+, zero runtime deps

---

## Executive Summary

ExecutionKit is a well-architected, cleanly layered library. Frozen value types, async-first design, structural protocols, and a strict dependency DAG reflect mature engineering. The codebase is compact (~1 200 SLOC across 15 modules) with strong conventions already in place. This review surfaces 24 findings — none Critical, 3 High, 10 Medium, 11 Low — predominantly around encapsulation violations, missing defensive checks, and minor complexity/duplication patterns.

| Severity | Count |
|----------|-------|
| Critical | 0     |
| High     | 3     |
| Medium   | 10    |
| Low      | 11    |
| **Total** | **24** |

---

## Category 1: Code Complexity

### CQ-01 — `_extract_balanced` manual character-state machine (Medium)
**File:** `executionkit/engine/json_extraction.py:71-138`
**Description:** The balanced-brace extractor is a hand-rolled finite-state machine tracking `depth`, `in_string`, and `escape_next` across a character-by-character loop. Cyclomatic complexity is approximately 14 (multiple branching paths per character class). While functionally correct, this is the most complex function in the codebase and the hardest to modify safely.
**Risk:** High cognitive load for future maintainers; edge-case bugs in string-boundary tracking are easy to introduce.
**Recommendation:** Add an explanatory comment block at the top of the loop mapping each character class to its state transition. Consider extracting the string-tracking logic into a small helper (e.g., `_advance_string_state(char, in_string, escape_next) -> tuple[bool, bool]`) to flatten the nesting. Alternatively, add a dedicated property-based test (Hypothesis) to fuzz the parser with adversarial inputs.

### CQ-02 — `_extract_content` multi-format handling (Low)
**File:** `executionkit/provider.py:400-424`
**Description:** `_extract_content` handles `None`, `str`, `list[str]`, `list[dict]` with nested `text`/`value` lookups, and a fallback `str(content)`. The nested `isinstance` checks contribute moderate cyclomatic complexity (~8). The function covers Anthropic, OpenAI, and edge-case response formats, so the branching is inherently necessary.
**Recommendation:** No refactor needed at current size, but add inline comments mapping each branch to the provider format it handles (e.g., `# Anthropic content block`, `# OpenAI text output`). If a fourth format is added, extract a strategy pattern or dispatch table.

### CQ-03 — `react_loop` function length (Low)
**File:** `executionkit/patterns/react_loop.py:86-232`
**Description:** `react_loop` spans ~147 lines including docstring and metadata assembly. The core loop body is around 70 lines of logic, which is within acceptable limits but approaching the threshold where extraction improves readability.
**Recommendation:** Consider extracting the inner tool-call processing block (lines 206-226, the `for tc in response.tool_calls` loop) into a private helper such as `_process_tool_calls(response, tool_lookup, ...) -> list[dict]` that returns the tool-role messages. This would bring the main function under 50 lines of logic.

---

## Category 2: Maintainability

### MT-01 — `checked_complete` directly accesses `CostTracker._calls` (High)
**File:** `executionkit/patterns/base.py:87,96`
**Description:** `checked_complete` manipulates the private field `tracker._calls += 1` and `tracker._calls -= 1` to implement TOCTOU-safe pre-increment of the call counter. This breaks encapsulation: any rename or restructuring of `CostTracker` internals will silently break `checked_complete`. The comment justifying this is good, but the pattern is fragile.
**Recommendation:** Add explicit public methods to `CostTracker`:
```python
def reserve_call(self) -> None:
    """Pre-increment call count to reserve a slot (TOCTOU safety)."""
    self._calls += 1

def release_call(self) -> None:
    """Release a previously reserved call slot on failure."""
    self._calls -= 1
```
Then replace `tracker._calls += 1` with `tracker.reserve_call()` and `tracker._calls -= 1` with `tracker.release_call()`. This preserves the TOCTOU fix while keeping encapsulation intact.

### MT-02 — `_note_truncation` mutates metadata dict in place (Medium)
**File:** `executionkit/patterns/base.py:102-119`
**Description:** `_note_truncation` receives a `dict[str, Any]` and increments a counter inside it. The function signature gives no indication that it mutates its argument. While this is a private helper, mutation-as-side-effect makes reasoning about metadata state harder, especially in `react_loop` where metadata is mutated from multiple call sites.
**Recommendation:** Either (a) rename to `_record_truncation` and document the mutation in the docstring, or (b) return the updated count and let the caller assign. Option (a) is simplest and sufficient for a private helper.

### MT-03 — `ConvergenceDetector` is a mutable dataclass (Low)
**File:** `executionkit/engine/convergence.py:9-68`
**Description:** `ConvergenceDetector` uses `@dataclass` (not `frozen=True`) because it maintains mutable internal state (`_scores`, `_stale_count`). This is intentional and documented. However, the `delta_threshold`, `patience`, and `score_threshold` configuration fields are also mutable, meaning a caller could accidentally reassign them mid-loop.
**Recommendation:** Consider making the configuration fields read-only via `__post_init__` validation, or document clearly that configuration must not be changed after construction. An alternative: split into a frozen config dataclass and a mutable state object.

### MT-04 — `Kit.react` uses `type: ignore[arg-type]` for provider cast (Low)
**File:** `executionkit/kit.py:71`
**Description:** `Kit.react` passes `self.provider` (typed as `LLMProvider`) to `react_loop` (which expects `ToolCallingProvider`), suppressing the type error with `# type: ignore[arg-type]`. The runtime check in `react_loop` guards against this, but the suppression hides a genuine type gap.
**Recommendation:** Add an overloaded `__init__` or a separate `ToolKit` class, or use `cast` with an explicit runtime assertion at the `Kit.react` call site rather than silencing the type checker. Alternatively, add a descriptive comment explaining the intentional widening and that `react_loop` performs its own runtime check.

### MT-05 — `MockProvider.calls` uses mutable list as default field (Low)
**File:** `executionkit/_mock.py:41`
**Description:** `calls: list[_CallRecord] = field(default_factory=list, init=False)` is correct (uses `field(default_factory=...)`), but the `responses` field at line 39 also uses `field(default_factory=list)`. A user passing `responses=some_list` shares the reference. This is standard Python dataclass behavior, but since `MockProvider._index` cycles over the list, external mutation of the passed-in list would silently change mock behavior.
**Recommendation:** Consider copying the input in `__post_init__`: `object.__setattr__(self, 'responses', list(self.responses))`. Low priority since this is a test utility.

---

## Category 3: Code Duplication

### DU-01 — HTTP error handling duplicated between `_post_httpx` and `_post_urllib` (High)
**File:** `executionkit/provider.py:296-372`
**Description:** Both `_post_httpx` (lines 296-327) and `_post_urllib` (lines 329-372) contain nearly identical error-classification logic: check for 429 -> `RateLimitError`, check for 401/403/404 -> `PermanentError`, else -> `ProviderError`. The status-code-to-exception mapping is duplicated across both methods with minor structural differences.
**Recommendation:** Extract a shared helper:
```python
def _classify_http_error(
    status: int,
    payload: dict[str, Any],
    retry_after: float = 1.0,
) -> LLMError:
    if status == 429:
        return RateLimitError("Rate limited (HTTP 429)", retry_after=retry_after)
    if status in {401, 403, 404}:
        return PermanentError(_format_http_error(status, payload))
    return ProviderError(_format_http_error(status, payload))
```
Both `_post_httpx` and `_post_urllib` would then call `raise _classify_http_error(status, raw, retry_after) from exc`. This ensures error-mapping logic evolves in one place.

### DU-02 — Budget-check triplet repeated in `checked_complete` (Medium)
**File:** `executionkit/patterns/base.py:66-84`
**Description:** Three near-identical `if budget.X > 0 and current.X >= budget.X` checks exist for `llm_calls`, `input_tokens`, and `output_tokens`. Each differs only in the field name and error message string.
**Recommendation:** Extract a loop over field descriptors:
```python
_BUDGET_FIELDS = [
    ("llm_calls", "LLM call"),
    ("input_tokens", "Input token"),
    ("output_tokens", "Output token"),
]
for field_name, label in _BUDGET_FIELDS:
    limit = getattr(budget, field_name)
    used = getattr(current, field_name)
    if limit > 0 and used >= limit:
        raise BudgetExhaustedError(f"{label} budget exhausted before dispatch", ...)
```
This eliminates the repetition and makes adding new budget dimensions trivial.

### DU-03 — Score range validation duplicated (Medium)
**File:** `executionkit/patterns/refine_loop.py:38-42,47-50` and `executionkit/patterns/base.py:30-32` and `executionkit/engine/convergence.py:43-44`
**Description:** The score range check `0.0 <= score <= 1.0` (or `0.0 <= score <= 10.0` for raw scores) appears in three separate locations with slightly different error messages and ranges. `validate_score` in `base.py` handles the `[0, 1]` case. `_parse_score` in `refine_loop.py` checks `[0, 10]` inline. `ConvergenceDetector.should_stop` checks `[0, 1]` independently.
**Recommendation:** Have `ConvergenceDetector.should_stop` call `validate_score` from `patterns.base` instead of inlining its own check. For `_parse_score`, the `[0, 10]` range is different so a separate check is appropriate, but consider extracting a `_validate_raw_score(score, lo, hi)` to normalize the pattern.

### DU-04 — Metadata dict construction pattern repeated (Low)
**File:** `executionkit/patterns/consensus.py:113-118`, `executionkit/patterns/refine_loop.py:209-218`, `executionkit/patterns/react_loop.py:180-185`
**Description:** Every pattern ends with `PatternResult(value=..., score=..., cost=tracker.to_usage(), metadata=MappingProxyType({...}))`. The `cost=tracker.to_usage()` + `MappingProxyType(dict(...))` wrapping is a minor but consistent pattern.
**Recommendation:** Low priority. Could extract a `_make_result(value, score, tracker, **metadata_fields)` helper into `patterns/base.py`, but the current explicit construction is clear and the duplication is only 3 instances. Acknowledge and defer.

---

## Category 4: Clean Code / SOLID Principles

### SO-01 — `Provider` class has multiple responsibilities (Medium)
**File:** `executionkit/provider.py:196-387`
**Description:** `Provider` handles HTTP transport (two backends), JSON serialization, response parsing, error classification, credential management, and resource lifecycle (`aclose`, context manager). This is approximately four concerns: transport, serialization, error mapping, and lifecycle. The class is ~190 lines.
**Recommendation:** The current design is pragmatic for a zero-dependency library and splitting would add unnecessary abstraction for the current scale. However, if a third transport backend is added (e.g., `aiohttp`), extract an `HttpBackend` protocol with `post(url, body, headers) -> dict` implementations. The response parsing (`_parse_response`, `_first_choice`, etc.) is already well-factored as module-level functions.

### SO-02 — `_TrackedProvider` violates Interface Segregation (Medium)
**File:** `executionkit/patterns/base.py:122-170`
**Description:** `_TrackedProvider` hardcodes `supports_tools: Literal[True] = True` regardless of whether the wrapped provider actually supports tools. This means wrapping a non-tool-calling provider in `_TrackedProvider` would falsely advertise tool support. Currently `_TrackedProvider` is only used internally by patterns that don't require tool calling, but the unconditional `True` is misleading.
**Recommendation:** Delegate `supports_tools` to the wrapped provider:
```python
@property
def supports_tools(self) -> bool:
    return getattr(self._provider, "supports_tools", False)
```
Or remove the attribute entirely if `_TrackedProvider` is never passed to `react_loop`.

### SO-03 — `pipe` error augmentation mutates exception in place (Medium)
**File:** `executionkit/compose.py:121-123`
**Description:** `exc.cost = total_cost + exc.cost` mutates the caught exception's `cost` attribute to include accumulated cross-step costs. This is a side effect on the exception object. While useful for callers, mutation of a caught exception is surprising.
**Recommendation:** Document this behavior explicitly in `pipe`'s docstring under a "Cost augmentation" section. The alternative (wrapping in a new exception) would lose the original exception type, so mutation is the pragmatic choice here. Adding a note is sufficient.

### SO-04 — Open/Closed principle: `_extract_content` format dispatch (Low)
**File:** `executionkit/provider.py:400-424`
**Description:** Each new LLM response format requires modifying the `if/elif` chain in `_extract_content`. This is a minor OCP concern.
**Recommendation:** Acceptable at current scale (3 formats). If growth continues, refactor to a list of `ContentExtractor` callables tried in order. Defer until a fourth format appears.

### SO-05 — `react_loop` performs both protocol validation and business logic (Low)
**File:** `executionkit/patterns/react_loop.py:139-145`
**Description:** The `isinstance(provider, ToolCallingProvider)` check at the top of `react_loop` mixes input validation with pattern logic. This is a minor SRP concern.
**Recommendation:** Acceptable. The check is two lines and fails fast. No action needed.

---

## Category 5: Technical Debt

### TD-01 — No `__all__` enforcement mechanism (Medium)
**File:** `executionkit/__init__.py:48-87`
**Description:** `__all__` lists 30+ names but there is no automated check that every public name is actually exported, or that `__all__` stays in sync with actual module-level names. `consensus_sync`, `refine_loop_sync`, etc. are in `__all__` and defined in the same file, but future additions could easily be missed.
**Recommendation:** Add a test that validates `__all__` matches actual module attributes:
```python
def test_all_exports_exist():
    import executionkit
    for name in executionkit.__all__:
        assert hasattr(executionkit, name), f"{name} in __all__ but not defined"
```

### TD-02 — `_HTTPX_AVAILABLE` / `_httpx` dual-flag pattern (Low)
**File:** `executionkit/provider.py:29-35`
**Description:** The module uses both `_HTTPX_AVAILABLE` (bool) and `_httpx` (module or None) to track httpx availability. The `_HTTPX_AVAILABLE` flag is redundant since `_httpx is not None` conveys the same information. Both are checked in `Provider.__post_init__` (line 222: `if _HTTPX_AVAILABLE and _httpx is not None`).
**Recommendation:** Remove `_HTTPX_AVAILABLE` and use `_httpx is not None` consistently. Low priority since both work correctly.

### TD-03 — `gather_resilient` bare `except asyncio.CancelledError: raise` (Low)
**File:** `executionkit/engine/parallel.py:36-37`
**Description:** The `try/except CancelledError: raise` block in `gather_resilient` is a no-op because `asyncio.gather(return_exceptions=True)` already captures exceptions as values and `CancelledError` propagates from the gather itself. The explicit re-raise is defensive but adds dead code.
**Recommendation:** Add a comment explaining why it exists (defensive against future `asyncio.gather` behavior changes) or remove the try/except entirely if testing confirms it is unreachable.

### TD-04 — Lazy `import logging` inside hot loop (Low)
**File:** `executionkit/patterns/react_loop.py:278`
**Description:** `import logging` is done inside `_execute_tool_call`'s exception handler. While Python caches module imports after the first load, the lazy import inside an exception handler is unconventional and adds a small overhead on the first failure.
**Recommendation:** Move `import logging` to module level. This is a single line change with no downside.

---

## Category 6: Error Handling

### EH-01 — `_post_httpx` silently swallows JSON parse errors from error responses (High)
**File:** `executionkit/provider.py:311-315`
**Description:**
```python
try:
    raw = exc.response.json()
    if not isinstance(raw, dict):
        raw = {}
except Exception:
    raw = {}
```
The bare `except Exception` catches *any* error during JSON parsing of an error response body, including `MemoryError`, `RecursionError`, or other unexpected failures. While pragmatic (error responses may not be JSON), the catch is overly broad.
**Recommendation:** Narrow to `except (json.JSONDecodeError, ValueError, UnicodeDecodeError):` to catch only expected parse failures. Let truly unexpected errors propagate.

### EH-02 — `consensus` does not validate `num_samples` (Medium)
**File:** `executionkit/patterns/consensus.py:23-118`
**Description:** `consensus` accepts `num_samples: int = 5` but does not validate that it is positive. Passing `num_samples=0` would produce an empty `coros` list, `gather_strict` would return `[]`, and the subsequent `counter.most_common()` would fail with an `IndexError` on line 101 — an unhelpful error.
**Recommendation:** Add a guard at the top:
```python
if num_samples < 1:
    raise ValueError("num_samples must be at least 1")
```

### EH-03 — `refine_loop` does not validate `max_iterations` (Low)
**File:** `executionkit/patterns/refine_loop.py:56-218`
**Description:** `max_iterations=0` is accepted without error. The loop body `for iteration in range(1, 0 + 1)` produces zero iterations, which is probably correct behavior (return the initial response). However, negative values would also silently produce zero iterations.
**Recommendation:** Add a guard: `if max_iterations < 0: raise ValueError(...)`. Zero is arguably valid (evaluate once, no refinement).

### EH-04 — `_parse_score` accepts scores like 0.5 as raw (in 0-10 range) (Low)
**File:** `executionkit/patterns/refine_loop.py:17-53`
**Description:** `_parse_score` validates against `[0, 10]`, but the caller divides by 10 (`raw_score / 10.0`). If the LLM returns `"0.5"`, `_parse_score` returns `0.5`, then the caller normalizes to `0.05`. This is technically correct but may be surprising — the LLM likely meant "5/10" quality. The score prompt asks for 0-10, so `0.5` is ambiguous.
**Recommendation:** Document this edge case in the `_parse_score` docstring. Consider adding a heuristic: if the parsed value is in `(0, 1)` exclusive and the regex matched it from a longer string, warn that the score may be on a 0-1 scale. Low priority — the ambiguity is inherent in LLM output.

---

## Summary of Recommendations by Priority

### Immediate (address before next release)
1. **MT-01:** Add `reserve_call`/`release_call` methods to `CostTracker` — eliminates private field access from outside the class.
2. **DU-01:** Extract `_classify_http_error` to deduplicate `_post_httpx`/`_post_urllib` error mapping.
3. **EH-01:** Narrow bare `except Exception` in `_post_httpx` JSON parsing to specific exception types.

### Short-term (next 2-3 sprints)
4. **DU-02:** Loop over budget fields instead of three copy-pasted checks.
5. **DU-03:** Have `ConvergenceDetector.should_stop` delegate to `validate_score`.
6. **EH-02:** Validate `num_samples >= 1` in `consensus`.
7. **SO-02:** Delegate `supports_tools` in `_TrackedProvider` to the wrapped provider.
8. **SO-03:** Document `pipe`'s exception cost-augmentation behavior.
9. **MT-02:** Rename `_note_truncation` to `_record_truncation` and document mutation.
10. **TD-01:** Add `test_all_exports_exist` to the test suite.

### Backlog (when touching these files)
11. **CQ-01:** Flatten `_extract_balanced` or add Hypothesis fuzzing.
12. **CQ-02:** Add format-mapping comments in `_extract_content`.
13. **CQ-03:** Extract tool-call processing from `react_loop`.
14. **MT-03:** Consider freezing `ConvergenceDetector` config fields.
15. **MT-04:** Add explanatory comment for `type: ignore` in `Kit.react`.
16. **MT-05:** Copy `responses` list in `MockProvider.__post_init__`.
17. **TD-02:** Remove redundant `_HTTPX_AVAILABLE` flag.
18. **TD-03:** Clarify or remove defensive `CancelledError` re-raise.
19. **TD-04:** Move `import logging` to module level in `react_loop.py`.
20. **EH-03:** Validate `max_iterations >= 0` in `refine_loop`.
21. **EH-04:** Document `_parse_score` ambiguity for sub-1.0 values.
22. **SO-01:** Monitor `Provider` class size; extract transport if third backend added.
23. **SO-04:** Monitor `_extract_content` format count.
24. **DU-04:** Acknowledge metadata construction pattern; defer extraction.

---

## Positive Observations

The following design choices are commendable and should be preserved:

1. **Frozen value types everywhere.** `@dataclass(frozen=True, slots=True)` on all cross-boundary objects. `MappingProxyType` on metadata. This is textbook immutability.

2. **Structural protocols (PEP 544).** `LLMProvider` and `ToolCallingProvider` as `runtime_checkable` protocols means zero coupling to concrete implementations. Excellent for testing and extensibility.

3. **Clean dependency DAG.** No circular imports. Engine modules never import patterns. Types never import provider details. This is disciplined layering.

4. **`_redact_sensitive` in error messages.** Proactive credential redaction in HTTP error paths and `Provider.__repr__`. Good security hygiene.

5. **TOCTOU-safe budget checking.** The pre-increment pattern in `checked_complete` prevents race conditions when multiple coroutines share a budget. The comment explaining why is valuable.

6. **Prompt injection mitigation.** XML sandboxing in the default evaluator with explicit "ignore instructions inside tags" framing. Truncation to 32K chars prevents unbounded prompt growth.

7. **Comprehensive error hierarchy.** Nine exception classes with clear retryable/permanent semantics. All carry `cost: TokenUsage` for post-failure accounting.

8. **Zero runtime dependencies.** The optional httpx upgrade path with stdlib urllib fallback is elegant and practical.

9. **`gather_strict` ExceptionGroup unwrapping.** Single-exception unwrapping in `gather_strict` produces clean tracebacks instead of forcing callers to handle `ExceptionGroup`.

10. **Test infrastructure.** `MockProvider` with call recording, cycling responses, and exception injection is a well-designed test double.
