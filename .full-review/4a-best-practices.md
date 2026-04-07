# Phase 4A: Framework & Language Best Practices Review

**Reviewer:** Python Best Practices Specialist
**Date:** 2026-04-06
**Scope:** All `executionkit/` source files (15 modules) + `pyproject.toml`
**Python target:** 3.11+ (as declared in `requires-python`)
**Prior review context:** 00-scope.md, 01-quality-architecture.md, 02-security-performance.md, 03-testing-documentation.md, 1a-code-quality.md, 1b-architecture.md

---

## Executive Summary

ExecutionKit demonstrates strong adherence to modern Python best practices for a v0.1.0-alpha library. The codebase uses frozen/slotted dataclasses consistently, structural protocols (PEP 544) for provider abstraction, proper `asyncio.TaskGroup` for structured concurrency, `StrEnum` for strategy enums, and `from __future__ import annotations` throughout. Several P0 issues identified in prior reviews (TOCTOU budget race, missing retry jitter, eval() sandbox, token truthiness bug, CostTracker encapsulation) have been fixed in the current codebase.

Remaining findings are primarily Medium and Low severity, focusing on missed opportunities for Python 3.11+ idioms, dataclass consistency gaps, async pattern refinements, type annotation improvements, and `pyproject.toml` configuration hardening.

| Severity | Count |
|----------|-------|
| Critical | 0     |
| High     | 2     |
| Medium   | 8     |
| Low      | 9     |
| **Total** | **19** |

---

## 1. Python 3.11+ Idioms

### BP-PY1 — `isinstance(x, (dict, list))` should use union syntax (Low)
**File:** `executionkit/engine/json_extraction.py` lines 43, 53, 62, 132
**Issue:** Four instances of `isinstance(result, (dict, list))` use the pre-3.10 tuple form. Since `requires-python = ">=3.11"`, the union syntax `isinstance(result, dict | list)` is idiomatic and would be flagged by Ruff `UP038`.
**Fix:** Replace all four with `isinstance(result, dict | list)`.

### BP-PY2 — HTTP status dispatch could use `match` statement (Low)
**Files:** `executionkit/provider.py` lines 317-327 (`_post_httpx`), lines 357-370 (`_post_urllib`)
**Issue:** Both HTTP backends use `if status == 429 ... if status in {401, 403, 404} ... raise` chains to classify HTTP errors. Python 3.10+ `match` statements are more readable and extensible for multi-branch dispatch on integer values.
**Example:**
```python
match status:
    case 429:
        raise RateLimitError(...)
    case 401 | 403 | 404:
        raise PermanentError(...)
    case _:
        raise ProviderError(...)
```
**Priority:** Low — the current `if/elif` works correctly. Only applicable if touching these methods for other reasons.

### BP-PY3 — `ExceptionGroup` unwrapping in `gather_strict` is correct and idiomatic (Positive)
**File:** `executionkit/engine/parallel.py` lines 71-73
**Observation:** The single-exception unwrapping `raise eg.exceptions[0] from eg` when `len(eg.exceptions) == 1` is the correct Python 3.11+ pattern for `TaskGroup`. This prevents callers from having to handle `ExceptionGroup` in the common single-failure case. Well done.

### BP-PY4 — `StrEnum` usage is correct and idiomatic (Positive)
**File:** `executionkit/types.py` line 102
**Observation:** `VotingStrategy(StrEnum)` uses Python 3.11's `StrEnum` correctly, enabling both enum-based logic (`if strategy == VotingStrategy.UNANIMOUS`) and string acceptance (`consensus(strategy="majority")` with `VotingStrategy(strategy)` conversion). Clean pattern.

### BP-PY5 — No use of `tomllib` (Low — informational)
**Issue:** Python 3.11 introduced `tomllib` for TOML reading. The library does not read TOML files at runtime (configuration is via constructor arguments), so this is not applicable. Noted for completeness — no action needed.

---

## 2. Async Patterns

### BP-AS1 — `asyncio.to_thread` without cancellation propagation (Medium)
**File:** `executionkit/provider.py` line 372, `_post_urllib`
**Issue:** When the calling task is cancelled (e.g., by `TaskGroup` unwinding or timeout), the `urllib` thread continues running until `request_timeout` (default 120s). Under high cancellation rates (e.g., budget exhaustion in `consensus` with many samples), orphaned threads pile up in the default executor. This is an inherent limitation of `asyncio.to_thread` with blocking I/O — Python provides no mechanism to interrupt a thread blocked in `urlopen`.
**Impact:** Thread pool exhaustion when cancellation is frequent. The default executor has `min(32, cpu_count + 4)` threads.
**Fix (near-term):** Document the thread-leak risk in the `_post_urllib` docstring. Consider reducing default `timeout` from 120s to 30s to bound the leak window.
**Fix (long-term):** Adopt `httpx.AsyncClient` as the primary transport (resolves this and PERF-03/PERF-06 simultaneously). The `_use_httpx` flag in `Provider` already enables this path when httpx is installed.

### BP-AS2 — `gather_resilient` defensive `except CancelledError: raise` is dead code (Low)
**File:** `executionkit/engine/parallel.py` lines 34-37
**Issue:** `asyncio.gather(return_exceptions=True)` never raises `CancelledError` — it captures it as a value in the results list. The outer `try/except asyncio.CancelledError: raise` is unreachable. While the intent (defensive against future asyncio behavior changes) is understandable, it adds dead code.
**Fix:** Remove the `try/except` wrapper, or add a comment explaining it is a defensive guard.

### BP-AS3 — `asyncio.Semaphore` correctly used for concurrency limiting (Positive)
**File:** `executionkit/engine/parallel.py`
**Observation:** Both `gather_resilient` and `gather_strict` correctly use `asyncio.Semaphore(max_concurrency)` to bound parallelism. The semaphore is created per-call (no shared state), which is correct for pattern-level concurrency control.

### BP-AS4 — Structured concurrency with `TaskGroup` is correct (Positive)
**File:** `executionkit/engine/parallel.py` lines 67-74
**Observation:** `gather_strict` uses `asyncio.TaskGroup` (Python 3.11+) for all-or-nothing semantics. The `ExceptionGroup` handling is correct. This is the recommended approach for structured concurrent execution.

---

## 3. Dataclass Patterns

### BP-DC1 — `ConvergenceDetector` missing `slots=True` (Medium)
**File:** `executionkit/engine/convergence.py` line 9
**Issue:** `@dataclass` without `slots=True`. Every other dataclass in the codebase uses `slots=True` (frozen dataclasses) or should use it (mutable ones). `slots=True` is valid on mutable dataclasses since Python 3.10 and provides:
- ~15-20% faster attribute access
- ~30% less memory per instance
- Prevents accidental attribute creation (typos like `detector.delat_threshold = 0.02` silently create a new attribute without slots)
**Fix:** `@dataclass(slots=True)`.

### BP-DC2 — `MockProvider` and `_CallRecord` missing `slots=True` (Medium)
**File:** `executionkit/_mock.py` lines 19, 29
**Issue:** Neither `_CallRecord` nor `MockProvider` uses `slots=True`. `MockProvider` is instantiated for every test case (324+ tests), so the memory overhead compounds. More importantly, the inconsistency with the rest of the codebase breaks the "slots everywhere" convention.
**Fix:** Add `slots=True` to both: `@dataclass(slots=True)`.
**Note:** `MockProvider` is not frozen (it mutates `calls` and `_index`), so `frozen=True` is not applicable, but `slots=True` works independently.

### BP-DC3 — `ConvergenceDetector.__eq__` compares internal state, not just configuration (Medium)
**File:** `executionkit/engine/convergence.py`
**Issue:** The auto-generated `__eq__` from `@dataclass` compares all fields including `_scores` and `_stale_count` (runtime state). Two detectors with identical configuration (`delta_threshold=0.01, patience=3`) but different call histories compare as unequal. This is surprising when comparing detector configurations in tests or caching.
**Fix:** Either `@dataclass(eq=False)` to suppress auto-generated `__eq__`, or explicitly exclude state fields via `field(compare=False)`:
```python
_scores: list[float] = field(default_factory=list, init=False, repr=False, compare=False)
_stale_count: int = field(default=0, init=False, repr=False, compare=False)
```
The `compare=False` approach is preferred — it preserves config-based equality while excluding mutable state.

### BP-DC4 — `LLMResponse` frozen dataclass contains mutable `list` and `dict` fields (High)
**File:** `executionkit/provider.py` lines 114-126
**Issue:** `LLMResponse` is `@dataclass(frozen=True, slots=True)` but has:
- `tool_calls: list[ToolCall]` — mutable `list` (though `ToolCall` items are frozen)
- `usage: dict[str, Any]` — mutable `dict`
- `raw: Any` — unconstrained

A consumer can do `response.tool_calls.append(ToolCall(...))` or `response.usage["custom"] = 42` without raising `FrozenInstanceError`. The `frozen=True` only prevents field reassignment, not mutation of mutable field values. This violates the library's documented immutability contract.
**Fix:** Coerce to immutable types in `_parse_response()` or via `__post_init__`:
```python
def __post_init__(self) -> None:
    object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
    object.__setattr__(self, "usage", MappingProxyType(self.usage))
```
Change the type annotations to `tool_calls: tuple[ToolCall, ...] = ()` and `usage: MappingProxyType[str, Any]` (or keep `dict` for init and coerce in `__post_init__`).

### BP-DC5 — `Tool.parameters` is a mutable `dict` on a frozen dataclass (Medium)
**File:** `executionkit/types.py` line 82
**Issue:** `Tool` is `frozen=True, slots=True` but `parameters: dict[str, Any]` is a plain mutable dict. A caller could mutate the schema after construction. Since `to_schema()` reads from `parameters` directly and `_validate_tool_args` in `react_loop.py` inspects it at call time, mutation between registration and invocation could cause silent behavior changes.
**Fix:** Wrap in `MappingProxyType` in `__post_init__`:
```python
def __post_init__(self) -> None:
    object.__setattr__(self, "parameters", MappingProxyType(self.parameters))
```
Or document that callers must not mutate after construction.

### BP-DC6 — `Provider.__post_init__` correctly uses `object.__setattr__` for derived state (Positive)
**File:** `executionkit/provider.py` lines 219-229
**Observation:** The frozen `Provider` dataclass correctly uses `object.__setattr__` in `__post_init__` to initialize derived fields (`_client`, `_use_httpx`). This is the standard Python pattern for derived state on frozen dataclasses. Clean implementation.

---

## 4. Protocol Usage

### BP-PR1 — `_TrackedProvider.supports_tools` is unconditionally `True` (High)
**File:** `executionkit/patterns/base.py` line 129
**Issue:** `_TrackedProvider` hardcodes `supports_tools: Literal[True] = True` regardless of whether the wrapped provider actually supports tools. If `_TrackedProvider` were ever used to wrap a non-tool-calling provider (e.g., in a future pattern), it would falsely satisfy `isinstance(wrapped, ToolCallingProvider)` at runtime.
**Current risk:** Low in practice — `_TrackedProvider` is currently only used by `refine_loop` (which does not pass tools). But the class satisfies `ToolCallingProvider` protocol structurally, which is misleading.
**Fix:** Delegate to the wrapped provider:
```python
@property
def supports_tools(self) -> bool:
    return getattr(self._provider, "supports_tools", False)
```
Or remove the attribute entirely if `_TrackedProvider` is never used with `react_loop`.

### BP-PR2 — `runtime_checkable` protocols are correctly applied (Positive)
**File:** `executionkit/provider.py` lines 160, 179
**Observation:** Both `LLMProvider` and `ToolCallingProvider` are `@runtime_checkable`, enabling `isinstance()` checks in `react_loop` (line 139). The `ToolCallingProvider` correctly extends `LLMProvider` and adds only a `supports_tools: Literal[True]` attribute. This is textbook PEP 544 usage.

### BP-PR3 — `PatternStep` protocol is correctly defined (Positive)
**File:** `executionkit/compose.py` lines 20-35
**Observation:** The `PatternStep` protocol specifies the minimal callable interface for pipe steps. The `_filter_kwargs` function correctly inspects step signatures to avoid passing unsupported keyword arguments. Good structural subtyping design.

---

## 5. Type Annotation Completeness and Correctness

### BP-TY1 — Sync wrappers use `cast()` instead of typed `_run_sync` (Medium)
**File:** `executionkit/__init__.py` lines 95-107, 119, 126, 138, 148
**Issue:** `_run_sync` returns `Any`, requiring four `cast("PatternResult[str]", ...)` calls in the sync wrappers. This bypasses type checking — if a pattern's return type ever changed, the cast would silently mask the mismatch.
**Fix:** Type `_run_sync` with a `TypeVar` so inference flows through:
```python
from typing import TypeVar
from collections.abc import Coroutine

_T = TypeVar("_T")

def _run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    ...
```
This eliminates all four `cast()` calls and makes the sync wrappers type-safe.

### BP-TY2 — `pipe_sync` accepts `*steps: Any` instead of `*steps: PatternStep` (Low)
**File:** `executionkit/__init__.py` line 144
**Issue:** `pipe_sync` declares `*steps: Any` while the async `pipe()` uses `*steps: PatternStep`. This loses the type contract for the synchronous entry point.
**Fix:** Change to `*steps: PatternStep`.

### BP-TY3 — `gather_resilient` return type `list[Any | BaseException]` is redundant (Low)
**File:** `executionkit/engine/parallel.py` line 15
**Issue:** `Any` already encompasses `BaseException` (and all types). `Any | BaseException` is a no-op union that communicates intent poorly. Ruff `PYI016` would flag this in `.pyi` stubs.
**Fix:** `-> list[Any]` with a docstring note explaining that exceptions appear as values in the result list. The current docstring already explains this behavior.

### BP-TY4 — `checked_complete` private field access on `tracker._calls` (Medium — encapsulation)
**File:** `executionkit/patterns/base.py` lines 87, 96
**Issue:** `checked_complete` directly accesses `tracker._calls += 1` and `tracker._calls -= 1` for the TOCTOU-safe pre-increment pattern. While `CostTracker` now has `record_without_call()` (which is used on line 98), the pre-increment and rollback still reach into private state. `CostTracker` lacks explicit `reserve_call()` / `release_call()` methods.
**Fix:** Add to `CostTracker`:
```python
def reserve_call(self) -> None:
    """Pre-increment call count to reserve a slot (TOCTOU safety)."""
    self._calls += 1

def release_call(self) -> None:
    """Release a previously reserved call slot on failure."""
    self._calls -= 1
```
Then replace `tracker._calls += 1` with `tracker.reserve_call()` and `tracker._calls -= 1` with `tracker.release_call()`.

### BP-TY5 — Complete type annotations verified (Positive)
**Observation:** `mypy --strict` passes with zero errors. All public function signatures have complete type annotations. `TYPE_CHECKING` guards are used correctly to prevent runtime circular imports (e.g., `cost.py` imports `LLMResponse` under `TYPE_CHECKING` only). The `from __future__ import annotations` import is present in every module for PEP 563 deferred evaluation.

---

## 6. `pyproject.toml` Best Practices

### BP-PT1 — `pre-commit-config.yaml` ruff version is stale (Low)
**File:** `.pre-commit-config.yaml` line 3
**Issue:** Uses `rev: v0.4.0` while `pyproject.toml` pins `ruff>=0.14.0,<0.15`. The pre-commit hook runs ruff 0.4 while CI and local dev use ruff 0.14+. This version mismatch means pre-commit may not catch rules added after ruff 0.4 (e.g., newer `UP`, `RUF` rules).
**Fix:** Update to `rev: v0.14.0` (or latest compatible) to match the pyproject pin.

### BP-PT2 — `pre-commit-config.yaml` mypy hook lacks `additional_dependencies` (Medium)
**File:** `.pre-commit-config.yaml` lines 9-12
**Issue:** The `mirrors-mypy` hook at `v1.10.0` runs mypy in an isolated environment without access to the project's dependencies. Type stubs for `httpx` and any other imported packages will be missing, potentially causing false positives or skipped checks. `pyproject.toml` pins `mypy>=1.18` — another version mismatch.
**Fix:** Add `additional_dependencies` to the hook:
```yaml
- id: mypy
  args: [--strict]
  additional_dependencies:
    - httpx>=0.27
  pass_filenames: false
  entry: mypy --strict executionkit/
```
Or update the rev to match the pyproject pin.

### BP-PT3 — Ruff rule selection is comprehensive and correct (Positive)
**File:** `pyproject.toml` lines 82-83
**Observation:** `select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "C4", "SIM", "TCH", "RUF"]` is an excellent selection covering errors, pyflakes, warnings, isort, naming, pyupgrade, bandit security, bugbear, shadowed builtins, comprehension simplification, simpleification, type-checking imports, and ruff-specific rules. Per-file ignores for tests (`S101`, `S105`, `S106`) correctly allow assertions and test credential patterns.

### BP-PT4 — Coverage configuration is well-structured (Positive)
**File:** `pyproject.toml` lines 68-80
**Observation:** Branch coverage enabled, `fail_under = 80`, `skip_empty = true`, and sensible exclusion lines (`TYPE_CHECKING`, `pragma: no cover`, `raise NotImplementedError`). The `[tool.pytest.ini_options]` section with `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"` addresses the pytest-asyncio deprecation warning correctly.

### BP-PT5 — Bandit configuration is appropriate (Positive)
**File:** `pyproject.toml` lines 91-97
**Observation:** Bandit excludes `tests/` and `examples/` and skips three justified rules: `B101` (assert), `B310` (urlopen — intentional for the HTTP client), `B311` (random.uniform — used for jitter, not cryptography). Each skip has a comment explaining why.

### BP-PT6 — `[project.urls]` uses placeholder URL (Low)
**File:** `pyproject.toml` lines 47-49
**Issue:** URLs point to `https://github.com/your-org/executionkit` — a placeholder that will 404 on PyPI. This should be updated before publishing.
**Fix:** Replace with actual repository URLs before the first PyPI release.

### BP-PT7 — No `py.typed` marker file (Low)
**File:** Missing `executionkit/py.typed`
**Issue:** The project declares `Typing :: Typed` in classifiers and has complete type annotations, but lacks the PEP 561 `py.typed` marker file. Without it, mypy and other type checkers will not recognize executionkit as a typed package when used as a dependency, falling back to untyped treatment.
**Fix:** Create an empty `executionkit/py.typed` file and ensure it is included in the wheel via hatch build config.

---

## 7. Deprecated APIs or Patterns

### BP-DP1 — No use of deprecated APIs detected (Positive)
**Observation:** The codebase does not use any deprecated Python stdlib APIs. Specific checks:
- No `asyncio.get_event_loop()` (deprecated for coroutines in 3.10+) — uses `asyncio.get_running_loop()` correctly in `_run_sync`
- No `@asyncio.coroutine` (removed in 3.11) — all coroutines use `async def`
- No `asyncio.Task.cancel(msg)` deprecation concerns — not used
- No `typing.Optional`, `typing.Union`, `typing.List`, `typing.Dict` — uses `X | None`, `list[T]`, `dict[K, V]` throughout (PEP 604/585)
- No `@typing.overload` misuse — not used
- No `collections.OrderedDict` where `dict` suffices — not present
- `StrEnum` is Python 3.11+ (not backported) — correct for `requires-python = ">=3.11"`

### BP-DP2 — `import logging` inside exception handler is unconventional (Low)
**File:** `executionkit/patterns/react_loop.py` line 278
**Issue:** `import logging` is done inside `_execute_tool_call`'s `except Exception` handler. While Python caches module imports after first load, the lazy import inside an exception handler is unconventional. Module-level imports are idiomatic Python and have negligible startup cost.
**Fix:** Move `import logging` to the module level (line 1-8 area). Single-line change.

---

## 8. Previously Identified Issues — Current Status

The following items from the prior `04-best-practices.md` have been resolved in the current codebase:

| Prior Finding | Status | Evidence |
|---------------|--------|----------|
| BP-H1: Phantom `pydantic` dependency | **FIXED** | `dependencies = []` in pyproject.toml |
| Retry jitter missing | **FIXED** | `random.uniform(0.0, cap)` in retry.py:50 |
| TOCTOU budget race | **FIXED** | Pre-increment in base.py:87-96 |
| Token truthiness bug | **FIXED** | Key-presence check in provider.py:131 |
| CostTracker encapsulation (add_usage, call_count) | **PARTIALLY FIXED** | `add_usage()`, `call_count`, `record_without_call()` exist; direct `_calls` access remains in `checked_complete` |
| Provider not frozen | **FIXED** | `@dataclass(frozen=True, slots=True)` on Provider |
| consensus whitespace normalization | **FIXED** | `_normalize()` function in consensus.py |
| eval() sandbox in examples | **FIXED** | AST-based `_safe_eval()` in react_tool_use.py |
| MaxIterationsError never raised | **FIXED** | `react_loop` raises it at line 228 |
| Missing pyproject metadata | **FIXED** | classifiers, authors, keywords, URLs present |
| Provider __repr__ masking | **FIXED** | Custom `__repr__` masks api_key |
| pytest-asyncio version pin | **FIXED** | `>=1.2` with `asyncio_default_fixture_loop_scope` |
| ruff version pin | **FIXED** | `>=0.14.0,<0.15` |
| Kit.__init__ accepts LLMProvider | **FIXED** | `provider: LLMProvider` at kit.py:30 |
| Tool argument validation | **FIXED** | `_validate_tool_args()` in react_loop.py |
| `react_loop` message trimming | **FIXED** | `_trim_messages()` + `max_history_messages` parameter |
| Default evaluator XML sandboxing | **FIXED** | XML tags + "ignore instructions" framing in refine_loop.py |

---

## Summary of New Findings

### Immediate (fix before next release)

| # | Sev | Finding | File(s) |
|---|-----|---------|---------|
| BP-DC4 | High | `LLMResponse` frozen dataclass has mutable `list`/`dict` fields | `provider.py` |
| BP-PR1 | High | `_TrackedProvider.supports_tools` unconditionally `True` | `patterns/base.py` |
| BP-TY4 | Med | `checked_complete` still accesses `tracker._calls` directly | `patterns/base.py`, `cost.py` |
| BP-PT2 | Med | Pre-commit mypy hook version mismatch + missing deps | `.pre-commit-config.yaml` |

### Short-term (next 2-3 sprints)

| # | Sev | Finding | File(s) |
|---|-----|---------|---------|
| BP-DC1 | Med | `ConvergenceDetector` missing `slots=True` | `engine/convergence.py` |
| BP-DC2 | Med | `MockProvider`/`_CallRecord` missing `slots=True` | `_mock.py` |
| BP-DC3 | Med | `ConvergenceDetector.__eq__` compares runtime state | `engine/convergence.py` |
| BP-DC5 | Med | `Tool.parameters` mutable dict on frozen dataclass | `types.py` |
| BP-TY1 | Med | Sync wrappers use `cast()` instead of typed `_run_sync` | `__init__.py` |
| BP-AS1 | Med | `asyncio.to_thread` thread-leak on cancellation | `provider.py` |

### Backlog (when touching these files)

| # | Sev | Finding | File(s) |
|---|-----|---------|---------|
| BP-PY1 | Low | `isinstance(x, (dict, list))` → union syntax | `json_extraction.py` |
| BP-PY2 | Low | HTTP status `if/elif` → `match` statement | `provider.py` |
| BP-AS2 | Low | Dead `except CancelledError` in `gather_resilient` | `parallel.py` |
| BP-TY2 | Low | `pipe_sync` accepts `*steps: Any` not `PatternStep` | `__init__.py` |
| BP-TY3 | Low | `gather_resilient` redundant `Any | BaseException` return type | `parallel.py` |
| BP-PT1 | Low | Pre-commit ruff version stale (0.4 vs 0.14) | `.pre-commit-config.yaml` |
| BP-PT6 | Low | `[project.urls]` uses placeholder URL | `pyproject.toml` |
| BP-PT7 | Low | Missing `py.typed` PEP 561 marker | `executionkit/` |
| BP-DP2 | Low | `import logging` inside exception handler | `react_loop.py` |

---

## Positive Observations

The following practices are commendable and should be preserved:

1. **Consistent `frozen=True, slots=True`** on all cross-boundary value types (`TokenUsage`, `PatternResult`, `Tool`, `ToolCall`, `LLMResponse`, `Provider`, `RetryConfig`). Textbook immutability.

2. **PEP 544 structural protocols** for `LLMProvider` and `ToolCallingProvider`. Zero coupling to concrete implementations. Correct `@runtime_checkable` usage.

3. **`from __future__ import annotations`** in every module. Enables PEP 563 deferred evaluation, preventing circular import issues and enabling forward references.

4. **`StrEnum`** for `VotingStrategy`. Enables both type-safe enum comparison and ergonomic string acceptance.

5. **`asyncio.TaskGroup`** in `gather_strict`. Correct structured concurrency with proper `ExceptionGroup` unwrapping.

6. **Full jitter in retry backoff** (`random.uniform(0.0, cap)`). Prevents thundering herd under concurrent rate limiting.

7. **AST-based safe math evaluator** in examples. Replaced the prior `eval()` sandbox with a proper whitelist visitor pattern.

8. **Comprehensive Ruff rule selection** covering 13 rule categories. Per-file ignores for tests are appropriate.

9. **`_redact_sensitive`** in HTTP error paths. Proactive credential sanitization using regex pattern matching.

10. **Zero runtime dependencies.** `dependencies = []` with optional `httpx` extra. The stdlib `urllib` fallback is elegant for environments where httpx is unavailable.
