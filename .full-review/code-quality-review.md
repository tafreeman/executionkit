# ExecutionKit -- Comprehensive Code Quality Review

**Reviewer:** Claude Opus 4.6 (code-reviewer)
**Date:** 2026-04-05
**Scope:** Full library source (`executionkit/`), tests (`tests/`), examples, config
**Commit:** `eba717d` (main)

## Summary

ExecutionKit is a well-structured, focused library. The overall code quality is high: 217 tests pass, ruff and mypy --strict report zero issues, and branch coverage is 84%. The design follows immutable value types, clean async patterns, and a clear error hierarchy. The findings below are genuine improvement opportunities, not cosmetic nitpicks.

**Findings by severity:**

| Severity | Count |
|----------|-------|
| Critical | 0     |
| High     | 3     |
| Medium   | 8     |
| Low      | 5     |

---

## HIGH Severity

### H1. `Kit._record` bypasses `CostTracker` encapsulation

**File:** `executionkit/kit.py`, lines 39-44
**Category:** Clean Code / Encapsulation violation

`Kit._record` directly mutates the private attributes `_tracker._input`, `_tracker._output`, and `_tracker._calls` instead of using the tracker's own interface.

```python
# Current (kit.py:42-44)
self._tracker._input += cost.input_tokens
self._tracker._output += cost.output_tokens
self._tracker._calls += cost.llm_calls
```

This creates a hidden coupling to `CostTracker`'s internal representation. If `CostTracker` were ever refactored (e.g., to use a list of snapshots, or to add thread safety), `Kit` would silently break.

**Recommendation:** Add a `record_usage(usage: TokenUsage)` method to `CostTracker` and call it from `Kit._record`.

```python
# cost.py — add method
def record_usage(self, usage: TokenUsage) -> None:
    """Record token usage from a pattern result."""
    self._input += usage.input_tokens
    self._output += usage.output_tokens
    self._calls += usage.llm_calls

# kit.py — use the public API
def _record(self, cost: TokenUsage) -> None:
    if self._tracker is not None:
        self._tracker.record_usage(cost)
```

---

### H2. `checked_complete` accesses `CostTracker._calls` directly

**File:** `executionkit/patterns/base.py`, line 70
**Category:** Clean Code / Encapsulation violation

```python
if budget.llm_calls > 0 and tracker._calls >= budget.llm_calls:
```

This is the same encapsulation breach as H1 but in a different module. The `_calls` attribute is a private implementation detail of `CostTracker`.

**Recommendation:** Expose `llm_calls` as a read-only property on `CostTracker`.

```python
# cost.py
@property
def llm_calls(self) -> int:
    """Number of LLM calls recorded so far."""
    return self._calls
```

Then change `base.py` line 70 to `tracker.llm_calls >= budget.llm_calls`.

---

### H3. `LLMResponse` token fallback logic has a subtle truthiness bug

**File:** `executionkit/provider.py`, lines 96-103
**Category:** Correctness / Subtle bug

```python
@property
def input_tokens(self) -> int:
    u = self.usage
    return int(u.get("input_tokens", 0) or u.get("prompt_tokens", 0))
```

The `or` operator uses Python truthiness, so when `input_tokens` is explicitly `0` (a valid value), it falls through to `prompt_tokens`. This means if a provider reports `{"input_tokens": 0, "prompt_tokens": 99}`, the library returns `99` instead of `0`.

The existing test at `test_provider.py:216-222` (`test_dual_format_falls_back_to_prompt_tokens_when_input_zero`) documents this behavior as intentional, but the docstring says the class "handles both OpenAI and Anthropic usage key formats" -- it does not document that `0` is treated as "absent." An API that legitimately returns `input_tokens: 0` (e.g., a cached response) would produce incorrect token tracking.

**Recommendation:** Use an explicit `None` sentinel check instead of truthiness.

```python
@property
def input_tokens(self) -> int:
    u = self.usage
    val = u.get("input_tokens")
    if val is not None:
        return int(val)
    return int(u.get("prompt_tokens", 0))

@property
def output_tokens(self) -> int:
    u = self.usage
    val = u.get("output_tokens")
    if val is not None:
        return int(val)
    return int(u.get("completion_tokens", 0))
```

The test `test_dual_format_falls_back_to_prompt_tokens_when_input_zero` would need updating to expect `0` as the correct return value.

---

## MEDIUM Severity

### M1. `Pydantic` is declared as a dependency but never used

**File:** `pyproject.toml`, line 12
**Category:** Technical debt / Dependency hygiene

```toml
dependencies = [
    "pydantic>=2.0,<3",
]
```

No file in `executionkit/` imports or references Pydantic. All value types use `dataclasses`. This adds an unnecessary transitive dependency tree (~5+ packages) for users who install ExecutionKit.

**Recommendation:** Remove `pydantic` from dependencies. If Pydantic support is planned for a future version, document it in the roadmap and add it when actually needed, or move it to an optional `[pydantic]` extra.

---

### M2. `Provider` is a mutable dataclass -- inconsistent with library's immutability stance

**File:** `executionkit/provider.py`, line 147
**Category:** Design consistency / Immutability violation

All other dataclasses in the library use `frozen=True, slots=True`. `Provider` uses bare `@dataclass`, making it mutable. A user could accidentally mutate `provider.model = "other"` mid-execution and corrupt a shared session.

**Recommendation:** Add `frozen=True, slots=True` to `Provider`:

```python
@dataclass(frozen=True, slots=True)
class Provider:
    ...
```

This is a minor breaking change (users assigning to fields after construction would break), but aligns with the library's stated philosophy.

---

### M3. `consensus` uses string equality for voting -- whitespace-sensitive

**File:** `executionkit/patterns/consensus.py`, lines 73-91
**Category:** Design robustness

```python
contents = [r.content for r in responses]
counter: collections.Counter[str] = collections.Counter(contents)
```

Two responses that differ only by trailing whitespace or newline (common with LLMs) are counted as distinct. This silently degrades agreement ratios and can cause `UNANIMOUS` to fail spuriously.

**Recommendation:** Strip/normalize content before counting:

```python
contents = [r.content.strip() for r in responses]
```

Or accept a `normalizer: Callable[[str], str] = str.strip` parameter for user control.

---

### M4. `refine_loop` default evaluator uses the same tracker as generation calls

**File:** `executionkit/patterns/refine_loop.py`, lines 100-123
**Category:** Design / Budget accounting

The default evaluator's `checked_complete` call on line 111 shares the same `tracker` and `max_cost` as the generation calls. This means evaluator LLM calls consume the same budget as generation calls. While this may be intentional, it is not documented and users would have no way to distinguish generation cost from evaluation cost in the metadata.

**Recommendation:** Document this explicitly in the `max_cost` parameter docstring. Alternatively, track evaluator calls separately and expose them in metadata (e.g., `evaluator_calls`).

---

### M5. `_parse_score` in `refine_loop` does not validate range

**File:** `executionkit/patterns/refine_loop.py`, lines 16-41
**Category:** Error handling / Input validation

`_parse_score` extracts a number from LLM output but does not validate that the number falls within the expected 0-10 range. The division by 10 on line 121 (`raw_score / 10.0`) would produce invalid scores if the LLM returns, say, `"42"` or `"-3"`. While `validate_score` is called afterward, an LLM returning `15` would produce `1.5`, which `validate_score` would catch -- but the error message would say "Invalid evaluator score: 1.5" rather than explaining the LLM returned an out-of-range value.

**Recommendation:** Add range clamping or a clearer error message in the default evaluator:

```python
raw_score = _parse_score(response.content)
normalized = raw_score / 10.0
if not (0.0 <= normalized <= 1.0):
    normalized = max(0.0, min(1.0, normalized))  # clamp
return normalized
```

---

### M6. No jitter in retry backoff

**File:** `executionkit/engine/retry.py`, lines 39-44
**Category:** Production robustness

```python
def get_delay(self, attempt: int) -> float:
    return min(
        self.base_delay * (self.exponential_base ** (attempt - 1)),
        self.max_delay,
    )
```

Exponential backoff without jitter causes "thundering herd" problems when many concurrent clients retry at the same cadence. For a library designed for parallel LLM calls (e.g., `consensus` with 5+ concurrent requests), this is particularly relevant.

**Recommendation:** Add a `jitter` parameter (default `True`) that applies uniform random jitter:

```python
import random

def get_delay(self, attempt: int) -> float:
    delay = min(
        self.base_delay * (self.exponential_base ** (attempt - 1)),
        self.max_delay,
    )
    if self.jitter:
        delay = random.uniform(0, delay)  # noqa: S311
    return delay
```

---

### M7. `_extract_balanced` silently fails on mismatched brace types

**File:** `executionkit/engine/json_extraction.py`, lines 71-138
**Category:** Correctness / Edge case

The balanced-brace extraction tracks `{`/`[` and `}`/`]` with a single `depth` counter but does not verify that the closer type matches the opener type. Input like `{"key": [}]` would reach depth 0 at the `}` and attempt a `json.loads`, which would fail, and then raise "Found balanced braces but content is not valid JSON." This is an acceptable fallback since `json.loads` catches it, but the function could produce false matches on malformed input where a `]` happens to reach depth 0 before the actual JSON ends.

**Recommendation:** Use a stack-based approach to match opener/closer types, or document the current behavior as a known limitation. Since `json.loads` validates the final candidate, this is more of a robustness concern than a bug.

---

### M8. `PatternResult.metadata` is a mutable dict on a frozen dataclass

**File:** `executionkit/types.py`, line 54
**Category:** Immutability / Design consistency

```python
@dataclass(frozen=True, slots=True)
class PatternResult(Generic[T]):
    metadata: dict[str, Any] = field(default_factory=dict)
```

While the dataclass is frozen (you cannot reassign `result.metadata = {}`), the dict itself is mutable. Users can do `result.metadata["injected"] = True` and mutate the result. Similarly, `LLMResponse.tool_calls` is a mutable `list` and `LLMResponse.usage` is a mutable `dict`. This is a common Python limitation with frozen dataclasses, but it weakens the immutability guarantee.

**Recommendation:** Use `MappingProxyType` or `types.MappingProxyType` to wrap metadata in a read-only view at construction, or document that the shallow freeze does not extend to container contents. For a v0.1, documenting the behavior is sufficient.

---

## LOW Severity

### L1. Sync wrappers in `__init__.py` are untested

**File:** `executionkit/__init__.py`, lines 84-139
**Category:** Test coverage gap

Coverage report shows lines 86-96, 108, 115, 127, 137 as uncovered. The sync wrappers (`consensus_sync`, `refine_loop_sync`, `react_loop_sync`, `pipe_sync`) and the `_run_sync` helper have zero test coverage. These are exported in `__all__` and part of the public API.

**Recommendation:** Add tests for:
1. `_run_sync` raising `RuntimeError` when called within an async context
2. Each `*_sync` wrapper returning the correct result type
3. Integration test confirming sync wrappers work from non-async code

---

### L2. `MockProvider` does not track `_index` correctly when exception is set

**File:** `executionkit/_mock.py`, lines 63-74
**Category:** Test infrastructure correctness

When `self.exception is not None`, the method raises before incrementing `_index`. This means if a test sets `exception` for one call, then clears it, the response index has not advanced. This is likely the intended behavior (exceptions don't consume a response), but it is undocumented.

**Recommendation:** Add a docstring note explaining that exceptions do not advance the response index.

---

### L3. `_FENCED_ANY_RE` in `json_extraction.py` requires opening `{` or `[`

**File:** `executionkit/engine/json_extraction.py`, line 18
**Category:** Documentation / Clarity

```python
_FENCED_ANY_RE = re.compile(r"```\s*\n?([\{\[].*?)```", re.DOTALL)
```

This pattern only matches code fences whose content starts with `{` or `[`. This is intentional (it avoids matching arbitrary code fences), but the comment on line 17 ("Pattern: ``` ... ``` (any code fence containing JSON)") is misleading -- it is not truly "any" code fence, only those starting with JSON-like characters.

**Recommendation:** Update the comment to: `# Pattern: ``` ... ``` (code fence starting with { or [)`.

---

### L4. `gather_resilient` `CancelledError` handling is redundant

**File:** `executionkit/engine/parallel.py`, lines 34-38
**Category:** Code cleanliness

```python
try:
    return await asyncio.gather(*[_run(c) for c in coros], return_exceptions=True)
except asyncio.CancelledError:
    raise
```

In Python 3.11+, `asyncio.CancelledError` is a subclass of `BaseException`, not `Exception`. The `except asyncio.CancelledError: raise` block is a no-op since `asyncio.gather` with `return_exceptions=True` does not catch `CancelledError` of the calling task in the first place. The explicit re-raise was likely added for Python 3.8 compatibility, which is not needed since the project requires 3.11+.

**Recommendation:** Remove the try/except wrapper or keep it with a comment explaining it is defensive.

---

### L5. `consensus` does not validate `num_samples >= 1`

**File:** `executionkit/patterns/consensus.py`, line 17
**Category:** Input validation

If `num_samples=0` is passed, the function creates zero coroutines, `gather_strict` returns `[]`, `contents` is empty, `Counter` is empty, and `most_common()` returns `[]`, causing an `IndexError` at line 89. Similarly, negative values would behave unexpectedly.

**Recommendation:** Add an early validation:

```python
if num_samples < 1:
    raise ValueError(f"num_samples must be >= 1, got {num_samples}")
```

---

## Positive Observations

These aspects of the codebase deserve recognition:

1. **Error hierarchy is well-designed.** Nine exception classes with clear parent/child relationships, clean separation between LLM errors and pattern errors, and appropriate retryable vs. permanent distinction.

2. **Frozen dataclasses with slots throughout.** Consistent use of `@dataclass(frozen=True, slots=True)` for value types delivers both immutability and memory efficiency.

3. **Structured concurrency via `TaskGroup`.** `gather_strict` uses `asyncio.TaskGroup` rather than raw `gather`, with correct single-exception unwrapping from `ExceptionGroup`.

4. **CancelledError propagation is handled correctly.** Both the retry engine and the react loop properly re-raise `asyncio.CancelledError` instead of catching it as a generic exception.

5. **Budget-checked completion is centralized.** The `checked_complete` helper in `base.py` provides a single enforcement point for budget checks, retry wrapping, and usage recording.

6. **Test quality is high.** 217 tests cover edge cases (NaN scores, budget exhaustion, tool timeouts, exception group unwrapping) and are organized by module with clear naming.

7. **Configuration is consolidated.** Single `pyproject.toml` for build, test, coverage, linting, and type checking -- no scattered config files.

8. **Zero external SDK dependencies for HTTP.** Using stdlib `urllib` with `asyncio.to_thread` keeps the dependency footprint minimal while supporting any OpenAI-compatible endpoint.

---

## Metrics Summary

| Metric | Value | Status |
|--------|-------|--------|
| Tests | 217 passed, 0 failed | PASS |
| Ruff lint | 0 issues | PASS |
| mypy --strict | 0 issues | PASS |
| Branch coverage | 84.21% | PASS (>80%) |
| Max file length | 258 lines (provider.py) | PASS (<400) |
| Max function length | ~50 lines (react_loop) | PASS |
| Cyclomatic complexity | Low across all modules | PASS |
