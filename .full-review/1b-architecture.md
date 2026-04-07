# Architecture Review: ExecutionKit

**Reviewer**: Software Architect Agent  
**Date**: 2026-04-06  
**Scope**: Structural integrity, component boundaries, dependency management, API design, data model, design patterns, architectural consistency  
**Files reviewed**: 16 source files, `pyproject.toml`, `docs/architecture.md`, `docs/api-reference.md`

---

## Executive Summary

ExecutionKit is a well-architected, minimal Python library for composable LLM reasoning patterns. The codebase demonstrates strong adherence to clean architecture principles: a strict layered dependency graph, frozen value types for immutability, protocol-based abstraction for provider extensibility, and a narrow public API surface. The design is lean and intentional, with few abstractions and no over-engineering.

The architecture is sound for a v0.1.0 library. The findings below are primarily Medium and Low severity, reflecting refinement opportunities rather than structural defects. Two High-severity findings address encapsulation violations and a missing abstraction that could bite as the library grows.

**Finding counts by severity:**
- **Critical**: 0
- **High**: 2
- **Medium**: 7
- **Low**: 5
- **Total**: 14

---

## 1. Component Boundaries

### 1.1 Module Cohesion Assessment

The package has a clear three-layer architecture:

| Layer | Modules | Responsibility |
|-------|---------|----------------|
| **Foundation** | `types.py`, `provider.py` | Value types, protocols, error hierarchy, concrete HTTP provider |
| **Engine** | `engine/convergence.py`, `engine/retry.py`, `engine/parallel.py`, `engine/json_extraction.py`, `cost.py` | Reusable infrastructure: retry, parallelism, convergence detection, cost tracking |
| **Patterns** | `patterns/base.py`, `patterns/consensus.py`, `patterns/refine_loop.py`, `patterns/react_loop.py`, `compose.py` | Business logic: reasoning patterns and composition |
| **Facade** | `kit.py`, `__init__.py` | Session wrapper and public API surface |

Each module is focused and cohesive. File sizes are appropriate (largest is `react_loop.py` at ~284 lines, well under the 400-line guideline).

### Finding 1.1 — `provider.py` has too many responsibilities

**Severity: Medium** | **Impact: Maintainability**

`provider.py` (511 lines) bundles four distinct concerns into a single module:
1. The error hierarchy (9 exception classes)
2. Value types (`ToolCall`, `LLMResponse`)
3. Protocols (`LLMProvider`, `ToolCallingProvider`)
4. The concrete `Provider` HTTP client with dual-backend logic

This is the largest file in the codebase and the most likely to grow. The HTTP parsing helpers (`_first_choice`, `_extract_content`, `_parse_tool_calls`, `_parse_tool_arguments`, `_load_json`, `_redact_sensitive`, `_format_http_error`) are all implementation details of the concrete `Provider` class but sit at module scope alongside the protocols and error hierarchy.

**Recommendation**: Extract the error hierarchy into `executionkit/errors.py` and consider extracting the concrete `Provider` into `executionkit/http_provider.py`. This would leave `provider.py` holding only the protocols and response value types, which is what most of the codebase actually imports from it. This refactor would not break the public API since `__init__.py` re-exports everything by name.

### Finding 1.2 — `_mock.py` imports from `provider.py` only

**Severity: Low** | **Impact: Positive observation**

`MockProvider` correctly depends only on `LLMResponse` from `provider.py`. It does not import pattern or engine modules. This clean boundary enables test code to use the mock without pulling in the full dependency graph.

---

## 2. Dependency Management

### 2.1 Dependency Graph Validation

The documented dependency direction (`types -> provider -> cost/engine -> patterns -> compose -> kit -> __init__`) was verified against actual imports:

```
types.py         -> (none; only TYPE_CHECKING import of LLMProvider)
provider.py      -> types
cost.py          -> types (runtime), provider (TYPE_CHECKING only)
engine/retry.py  -> provider (for error types)
engine/parallel.py -> (none; stdlib only)
engine/convergence.py -> (none; stdlib only)
engine/json_extraction.py -> (none; stdlib only)
patterns/base.py -> cost, engine/retry, provider, types
patterns/consensus.py -> cost, engine/parallel, engine/retry, patterns/base, provider, types
patterns/refine_loop.py -> cost, engine/convergence, engine/retry, patterns/base, provider, types
patterns/react_loop.py -> cost, engine/retry, patterns/base, provider, types
compose.py       -> provider, types
kit.py           -> compose, cost, patterns/*, provider, types
__init__.py      -> (everything)
```

**No circular dependencies detected.** The dependency graph is strictly acyclic and flows downward. `TYPE_CHECKING` guards are used correctly to prevent runtime circular imports (e.g., `cost.py` imports `LLMResponse` only under `TYPE_CHECKING`).

### Finding 2.1 — `engine/retry.py` couples the engine layer to provider error types

**Severity: Medium** | **Impact: Coupling**

`engine/retry.py` imports `ProviderError` and `RateLimitError` from `provider.py` to set them as the default retryable exceptions in `RetryConfig`. This creates a hard dependency from the engine layer up to the provider/foundation layer.

While pragmatic (the defaults are sensible), it means the engine layer cannot be used independently of the provider module. This is a minor layering violation: engine infrastructure should ideally be agnostic about what exceptions it retries.

**Recommendation**: Accept this as a pragmatic trade-off for v0.1.0, but if `RetryConfig` is ever extracted into a standalone utility, the default `retryable` tuple should move to the call site (e.g., `patterns/base.py`) rather than being baked into the engine-layer dataclass.

### Finding 2.2 — `compose.py` imports `ExecutionKitError` for error augmentation

**Severity: Low** | **Impact: Acceptable coupling**

`compose.py` catches `ExecutionKitError` in `pipe()` to augment `exc.cost` with accumulated cross-step costs before re-raising. This is a legitimate cross-cutting concern. The import is narrow and the behavior is well-documented.

---

## 3. API Design

### 3.1 Public Surface Assessment

The `__all__` list in `__init__.py` exports 37 symbols. This is a reasonable surface for the library's scope. All four pattern functions, the composition utility, the session facade, both protocols, all value types, the error hierarchy, and key engine utilities are exposed.

### Finding 3.1 — `_TrackedProvider` is private but architecturally significant

**Severity: Medium** | **Impact: Extensibility**

`_TrackedProvider` in `patterns/base.py` wraps an `LLMProvider` to automatically apply budget checking, retry logic, and truncation tracking. It is used only by `react_loop` (indirectly via `_note_truncation`) and could serve as a foundation for custom patterns.

However, it is marked private (`_` prefix) and is not exported. Custom pattern authors who want the same budget/retry/truncation integration must either:
- Call `checked_complete()` manually for each LLM call (as the current patterns do), or
- Duplicate the wrapper logic.

**Recommendation**: Consider promoting `_TrackedProvider` to a public utility (e.g., `TrackedProvider`) in the `patterns/base` module. Document it as the recommended way to build custom patterns that need multi-call budget tracking. This aligns with the documented extension point guidance in `docs/architecture.md`.

### Finding 3.2 — `consensus()` lacks `max_cost` budget parameter

**Severity: Medium** | **Impact: Consistency / Breaking change risk**

`refine_loop()` and `react_loop()` both accept `max_cost: TokenUsage | None` for budget enforcement. `consensus()` does not. It passes `budget=None` unconditionally to `checked_complete()`.

This is an API inconsistency. When `consensus()` is used as a step in `pipe()` with `max_budget`, the budget propagation mechanism (`pipe` forwards `max_cost` via `_filter_kwargs`) silently has no effect because `consensus` does not declare `max_cost` in its signature.

**Recommendation**: Add `max_cost: TokenUsage | None = None` to `consensus()` and pass it through to `checked_complete()`. This is additive (keyword-only, defaults to `None`) and would not break existing callers.

### Finding 3.3 — Sync wrappers use `cast()` rather than proper return types

**Severity: Low** | **Impact: Type safety**

The sync wrappers (`consensus_sync`, `refine_loop_sync`, etc.) in `__init__.py` use `cast("PatternResult[str]", ...)` to assert the return type. This is technically correct since `asyncio.run()` returns `Any`, but it bypasses type checking. If a pattern's return type ever changed, the cast would silently mask the mismatch.

**Recommendation**: This is acceptable for v0.1.0 since the sync wrappers are thin pass-throughs. No action needed unless the sync API grows.

### Finding 3.4 — `pipe_sync` accepts `*steps: Any` instead of `*steps: PatternStep`

**Severity: Low** | **Impact: Type safety**

In `__init__.py`, `pipe_sync` declares `*steps: Any` rather than `*steps: PatternStep`. This loses the type contract that exists on the async `pipe()` function.

**Recommendation**: Change to `*steps: PatternStep` to maintain type safety parity with the async version.

---

## 4. Data Model

### 4.1 Immutability Contract

All value types use `@dataclass(frozen=True, slots=True)`:
- `TokenUsage`, `PatternResult[T]`, `Tool`, `ToolCall`, `LLMResponse`, `Provider`, `RetryConfig`

`PatternResult.metadata` is additionally wrapped in `MappingProxyType` for read-only mapping semantics. The immutability contract is thoroughly enforced.

### Finding 4.1 — `LLMResponse` is frozen but contains mutable `list` and `dict` fields

**Severity: Medium** | **Impact: Immutability contract**

`LLMResponse` is `frozen=True` but has:
- `tool_calls: list[ToolCall]` — a mutable `list` (though contents are frozen `ToolCall` instances)
- `usage: dict[str, Any]` — a mutable `dict`
- `raw: Any` — unconstrained, could be mutable

A caller could do `response.tool_calls.append(...)` or `response.usage["extra"] = 1` and mutate the "frozen" object without error. The `frozen=True` only prevents *field reassignment* (`response.content = "new"` raises `FrozenInstanceError`), not mutation of mutable field values.

**Recommendation**: Wrap `tool_calls` in `tuple()` and `usage` in `MappingProxyType()` in `_parse_response()` or the `LLMResponse.__post_init__`. This would make the immutability contract truly deep. `raw` is harder to constrain but should at minimum be documented as "treat as read-only."

### Finding 4.2 — `Tool.parameters` is a mutable `dict[str, Any]`

**Severity: Medium** | **Impact: Immutability contract**

`Tool` is `frozen=True, slots=True` but `parameters: dict[str, Any]` is a plain mutable dict. A caller could mutate the schema after construction. Since `to_schema()` reads from `parameters` directly, this could cause surprising behavior if the schema is modified between tool registration and tool invocation.

**Recommendation**: Wrap `parameters` in `MappingProxyType` in a `__post_init__` (using `object.__setattr__` as done in `Provider`), or document that callers must not mutate it.

---

## 5. Design Patterns

### 5.1 Pattern Inventory

| Pattern | Where Used | Assessment |
|---------|-----------|------------|
| **Protocol (PEP 544)** | `LLMProvider`, `ToolCallingProvider`, `PatternStep` | Correct use. Runtime-checkable. Enables structural subtyping without inheritance. |
| **Frozen Value Object** | All value types | Comprehensive and consistent. |
| **Facade** | `Kit` class | Optional session wrapper. Clean delegation to standalone functions. |
| **Strategy** | `VotingStrategy` enum in `consensus` | Simple, appropriate. |
| **Decorator/Wrapper** | `_TrackedProvider` wrapping `LLMProvider` | Good internal use for cross-cutting budget/retry concerns. |
| **Template Method** | `checked_complete` as the standard LLM call path | Effective factoring of budget-check, retry, and recording. |
| **Pipeline** | `pipe()` function | Correct implementation of chain-of-responsibility for pattern composition. |

### Finding 5.1 — `checked_complete` directly mutates `CostTracker` private fields

**Severity: High** | **Impact: Encapsulation**

In `patterns/base.py`, `checked_complete()` directly accesses `tracker._calls`:

```python
tracker._calls += 1  # line 87
...
tracker._calls -= 1  # line 96 (on failure)
```

This breaks the encapsulation of `CostTracker`. The TOCTOU fix (pre-incrementing calls before yielding to the event loop) is the correct *behavior*, but it should be exposed through `CostTracker`'s public interface rather than reaching into private fields.

**Recommendation**: Add `reserve_call() -> None` and `release_call() -> None` methods to `CostTracker` that encapsulate the pre-increment/rollback pattern. The comment about TOCTOU safety belongs in the method docstring, not as an inline comment in a consumer module.

### Finding 5.2 — Missing abstraction for message construction

**Severity: High** | **Impact: Consistency / Duplication**

Every pattern constructs OpenAI-format message lists inline:
- `consensus.py`: `[{"role": "user", "content": prompt}]`
- `refine_loop.py`: Multi-message sequences with user/assistant/user structure
- `react_loop.py`: Message list with tool-role messages, assistant messages with `tool_calls`

The message format is duplicated across all pattern files and is tightly coupled to the OpenAI chat completions format. There is no message builder or message type abstraction.

This is acceptable at v0.1.0 with three patterns, but as new patterns are added, the repeated inline dict construction will become a maintenance burden and a source of subtle format inconsistencies (e.g., the `"content": response.content or None` in `react_loop.py` line 190 handles the null-content case differently than other patterns).

**Recommendation**: Introduce a thin message builder module (`executionkit/messages.py`) with helper functions:
- `user_message(content: str) -> dict[str, Any]`
- `assistant_message(content: str, tool_calls: list[ToolCall] | None = None) -> dict[str, Any]`
- `tool_message(tool_call_id: str, content: str) -> dict[str, Any]`

This would centralize the OpenAI format knowledge and make patterns easier to read and maintain.

### Finding 5.3 — `ConvergenceDetector` is a mutable `@dataclass` (not frozen)

**Severity: Low** | **Impact: Consistency**

`ConvergenceDetector` uses `@dataclass` (mutable) rather than `@dataclass(frozen=True)`. This is intentionally mutable (it tracks score history via `should_stop()` and has a `reset()` method), but it lacks `slots=True` which is used on all other dataclasses in the codebase.

**Recommendation**: Add `slots=True` for consistency and memory efficiency: `@dataclass(slots=True)`.

---

## 6. Architectural Consistency

### 6.1 Adherence to Stated Principles

The five design principles from `docs/architecture.md` were verified:

| Principle | Status | Notes |
|-----------|--------|-------|
| Zero runtime dependencies | **Verified** | `dependencies = []` in `pyproject.toml`. `httpx` is optional. |
| Flat package layout | **Verified** | No `src/` wrapper. Sub-packages for organization only. |
| Frozen value types | **Mostly verified** | See findings 4.1 and 4.2 for shallow freezing issues. |
| Async-first, sync wrappers | **Verified** | All patterns are `async`. Sync wrappers in `__init__.py`. |
| Composable, not opinionated | **Verified** | Patterns are standalone functions. `Kit` is optional. `pipe()` chains without coupling. |

### 6.2 Documentation-Code Alignment

The dependency graph in `docs/architecture.md` accurately reflects actual imports. The API reference in `docs/api-reference.md` is comprehensive and matches the source signatures. The error hierarchy diagram is accurate.

### Finding 6.1 — `consensus` is missing from the `pipe()` budget propagation path

**Severity: Medium** | **Impact: Documented behavior**

`docs/architecture.md` states: "pipe() propagates remaining budget per step with floor-at-zero subtraction." However, since `consensus()` does not accept `max_cost` (Finding 3.2), budget propagation silently fails when `consensus` is used as a pipe step. This is not documented as a limitation.

**Recommendation**: Either add `max_cost` to `consensus()` (preferred) or document this as a known limitation in the architecture docs and API reference.

---

## Summary of Findings

| # | Severity | Finding | Module(s) | Recommendation |
|---|----------|---------|-----------|----------------|
| 1.1 | Medium | `provider.py` bundles 4 concerns (511 lines) | `provider.py` | Extract errors to `errors.py`, consider `http_provider.py` |
| 2.1 | Medium | Engine layer coupled to provider error types | `engine/retry.py` | Accept for v0.1.0; move defaults to call site if extracting |
| 3.1 | Medium | `_TrackedProvider` is private but architecturally useful | `patterns/base.py` | Promote to public API for custom pattern authors |
| 3.2 | Medium | `consensus()` lacks `max_cost` budget parameter | `patterns/consensus.py` | Add `max_cost: TokenUsage \| None = None` |
| 3.3 | Low | Sync wrappers use `cast()` | `__init__.py` | Acceptable for v0.1.0 |
| 3.4 | Low | `pipe_sync` accepts `*steps: Any` | `__init__.py` | Change to `*steps: PatternStep` |
| 4.1 | Medium | `LLMResponse` has mutable list/dict fields on frozen dataclass | `provider.py` | Wrap in `tuple()` / `MappingProxyType` |
| 4.2 | Medium | `Tool.parameters` is mutable dict on frozen dataclass | `types.py` | Wrap in `MappingProxyType` in `__post_init__` |
| 5.1 | **High** | `checked_complete` mutates `CostTracker._calls` directly | `patterns/base.py`, `cost.py` | Add `reserve_call()` / `release_call()` to `CostTracker` |
| 5.2 | **High** | No message builder abstraction; format duplicated across patterns | `patterns/*.py` | Introduce `executionkit/messages.py` with helper functions |
| 5.3 | Low | `ConvergenceDetector` lacks `slots=True` | `engine/convergence.py` | Add `slots=True` for consistency |
| 6.1 | Medium | `consensus` silently ignores budget in `pipe()` chains | `patterns/consensus.py`, `compose.py` | Add `max_cost` to `consensus()` or document limitation |
| — | Low | `_mock.py` clean boundary (positive) | `_mock.py` | No action needed |
| — | Low | Documentation-code alignment verified (positive) | `docs/` | No action needed |

---

## Architectural Risk Assessment

### Low Risk
- **Breaking changes**: The public API is well-defined via `__all__`. All pattern functions accept `**kwargs`, which provides forward compatibility for adding new parameters.
- **Circular dependencies**: None detected. The layering is strict and clean.
- **Over-engineering**: The library is appropriately minimal. No unnecessary abstractions.

### Medium Risk
- **Shallow immutability** (Findings 4.1, 4.2): Mutable collections inside frozen dataclasses could cause subtle bugs in concurrent scenarios or when results are cached/shared.
- **Budget gap** (Findings 3.2, 6.1): The `consensus` pattern silently ignores budget constraints, which could lead to unexpected cost overruns in `pipe()` chains.

### Growth Concerns
- **Message format coupling** (Finding 5.2): As more patterns are added, the lack of a message builder will increase duplication and divergence risk.
- **Provider module size** (Finding 1.1): The `provider.py` module is the most likely growth point as new provider formats (Anthropic native, Gemini) are supported.

---

## Conclusion

ExecutionKit's architecture is clean, well-layered, and appropriate for its scope. The dependency graph is acyclic, value types are (mostly) immutable, the protocol-based provider abstraction is extensible, and the public API surface is well-controlled. The two High-severity findings (encapsulation violation in `checked_complete` and missing message abstraction) are the most important items to address before the library matures beyond v0.1.0. The Medium-severity findings around shallow immutability and budget consistency should be addressed in a near-term release to prevent them from becoming entrenched API contracts.
