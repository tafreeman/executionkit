# Phase 1: Code Quality & Architecture Review

**Sources:** `1a-code-quality.md` (24 findings), `1b-architecture.md` (14 findings)
**Date:** 2026-04-06
**Totals:** Critical: 0, High: 5, Medium: 17, Low: 16

---

## Code Quality Findings

### Critical
None.

### High

- **CQ-H1 (MT-01)** -- `checked_complete` directly accesses `CostTracker._calls` private field, breaking encapsulation. Add `reserve_call()`/`release_call()` methods to `CostTracker`. (`patterns/base.py:87,96`)
- **CQ-H2 (DU-01)** -- HTTP error-handling logic duplicated between `_post_httpx` and `_post_urllib` with identical status-code-to-exception mapping. Extract `_classify_http_error()`. (`provider.py:296-372`)
- **CQ-H3 (EH-01)** -- `_post_httpx` catches bare `except Exception` when parsing error response JSON, swallowing `MemoryError`/`RecursionError`. Narrow to `json.JSONDecodeError`/`ValueError`/`UnicodeDecodeError`. (`provider.py:311-315`)

### Medium

- **CQ-M1 (CQ-01)** -- `_extract_balanced` is a hand-rolled FSM with cyclomatic complexity ~14. Add explanatory comments or extract string-state helper. (`engine/json_extraction.py:71-138`)
- **CQ-M2 (MT-02)** -- `_note_truncation` mutates metadata dict in place without documenting the side effect. Rename or document mutation. (`patterns/base.py:102-119`)
- **CQ-M3 (DU-02)** -- Budget-check triplet (llm_calls, input_tokens, output_tokens) is copy-pasted 3x. Loop over field descriptors instead. (`patterns/base.py:66-84`)
- **CQ-M4 (DU-03)** -- Score range validation `0.0 <= score <= 1.0` duplicated across 3 modules with divergent ranges. Centralize via `validate_score`. (`refine_loop.py`, `base.py`, `convergence.py`)
- **CQ-M5 (SO-01)** -- `Provider` class has ~4 responsibilities (transport, serialization, error mapping, lifecycle) across ~190 lines. Monitor; extract transport if third backend added. (`provider.py:196-387`)
- **CQ-M6 (SO-02)** -- `_TrackedProvider` hardcodes `supports_tools: Literal[True] = True` regardless of wrapped provider capability. Delegate to wrapped provider. (`patterns/base.py:122-170`)
- **CQ-M7 (SO-03)** -- `pipe` error augmentation mutates caught exception's `cost` attribute in place. Document behavior in docstring. (`compose.py:121-123`)
- **CQ-M8 (EH-02)** -- `consensus` does not validate `num_samples >= 1`; passing `0` causes unhelpful `IndexError`. Add guard. (`patterns/consensus.py:23-118`)
- **CQ-M9 (TD-01)** -- No automated check that `__all__` stays in sync with actual module exports. Add `test_all_exports_exist`. (`__init__.py:48-87`)

### Low

- **CQ-L1 (CQ-02)** -- `_extract_content` multi-format branches lack inline comments mapping each branch to its provider format. (`provider.py:400-424`)
- **CQ-L2 (CQ-03)** -- `react_loop` spans ~147 lines; inner tool-call processing could be extracted. (`patterns/react_loop.py:86-232`)
- **CQ-L3 (MT-03)** -- `ConvergenceDetector` config fields are mutable despite being configuration. Consider freezing config. (`engine/convergence.py:9-68`)
- **CQ-L4 (MT-04)** -- `Kit.react` uses `type: ignore[arg-type]` to suppress genuine type gap between `LLMProvider` and `ToolCallingProvider`. (`kit.py:71`)
- **CQ-L5 (MT-05)** -- `MockProvider.responses` shares reference with caller; external mutation changes mock behavior. (`_mock.py:41`)
- **CQ-L6 (TD-02)** -- Redundant `_HTTPX_AVAILABLE` flag when `_httpx is not None` suffices. (`provider.py:29-35`)
- **CQ-L7 (TD-03)** -- `gather_resilient` has a no-op `except CancelledError: raise` on Python 3.11+. (`engine/parallel.py:36-37`)
- **CQ-L8 (TD-04)** -- Lazy `import logging` inside exception handler in `_execute_tool_call`. Move to module level. (`patterns/react_loop.py:278`)
- **CQ-L9 (EH-03)** -- `refine_loop` accepts negative `max_iterations` silently (produces zero iterations). Add guard. (`patterns/refine_loop.py:56-218`)
- **CQ-L10 (EH-04)** -- `_parse_score` treats LLM output `"0.5"` as 0.5/10 = 0.05 normalized; ambiguous edge case. Document. (`patterns/refine_loop.py:17-53`)
- **CQ-L11 (DU-04)** -- Metadata dict construction pattern (`PatternResult(... MappingProxyType({...}))`) repeated 3x. Acknowledge; defer extraction. (`consensus.py`, `refine_loop.py`, `react_loop.py`)
- **CQ-L12 (SO-04)** -- `_extract_content` if/elif chain requires modification for each new format (minor OCP). Defer until 4th format. (`provider.py:400-424`)
- **CQ-L13 (SO-05)** -- `react_loop` mixes protocol validation with business logic (minor SRP). Acceptable; 2 lines, fails fast. (`patterns/react_loop.py:139-145`)

---

## Architecture Findings

### Critical
None.

### High

- **AR-H1 (5.1)** -- `checked_complete` mutates `CostTracker._calls` directly, breaking encapsulation of the cost tracking boundary. Same root cause as CQ-H1. Add `reserve_call()`/`release_call()` public methods. (`patterns/base.py`, `cost.py`)
- **AR-H2 (5.2)** -- No message builder abstraction; OpenAI-format message dicts constructed inline across all 3 patterns with subtle format divergence. Introduce `executionkit/messages.py` with `user_message()`, `assistant_message()`, `tool_message()` helpers. (`patterns/*.py`)

### Medium

- **AR-M1 (1.1)** -- `provider.py` (511 lines) bundles error hierarchy, value types, protocols, and HTTP client. Extract `errors.py`; consider `http_provider.py`. (`provider.py`)
- **AR-M2 (2.1)** -- `engine/retry.py` imports provider error types, coupling engine layer to foundation. Pragmatic for v0.1.0; move defaults to call site if extracting. (`engine/retry.py`)
- **AR-M3 (3.1)** -- `_TrackedProvider` is private but architecturally significant for custom pattern authors. Promote to public API. (`patterns/base.py`)
- **AR-M4 (3.2 + 6.1)** -- `consensus()` lacks `max_cost` parameter; budget propagation silently fails when used as `pipe()` step. Add `max_cost: TokenUsage | None = None`. (`patterns/consensus.py`, `compose.py`)
- **AR-M5 (4.1)** -- `LLMResponse` is frozen but contains mutable `list[ToolCall]` and `dict` fields; shallow freeze allows mutation. Wrap in `tuple()`/`MappingProxyType()`. (`provider.py`)
- **AR-M6 (4.2)** -- `Tool.parameters` is a mutable `dict` on a frozen dataclass. Wrap in `MappingProxyType` in `__post_init__`. (`types.py`)
- **AR-M7 (A1)** -- `Kit.__init__` accepts concrete `Provider` instead of `LLMProvider` protocol, blocking custom providers at the type-checker level. Change annotation to `LLMProvider`. (`kit.py:30`)
- **AR-M8 (A2)** -- `MaxIterationsError` is exported in `__all__` but never raised by any pattern. Either raise it (opt-in `strict=True`) or remove from `__all__`. (`types.py`, `__init__.py`)

### Low

- **AR-L1 (3.3)** -- Sync wrappers use `cast()` rather than proper return types. Acceptable for v0.1.0. (`__init__.py`)
- **AR-L2 (3.4)** -- `pipe_sync` accepts `*steps: Any` instead of `*steps: PatternStep`. Change for type safety parity. (`__init__.py`)
- **AR-L3 (5.3)** -- `ConvergenceDetector` lacks `slots=True`, inconsistent with all other dataclasses. Add `slots=True`. (`engine/convergence.py`)

---

## Critical Issues for Phase 2 Context

These findings should directly inform the security and performance reviews:

- **CostTracker encapsulation (CQ-H1 / AR-H1):** Budget enforcement reads private fields directly. If `CostTracker` is subclassed or replaced, budget limits could be bypassed silently. Relevant to security (cost control bypass) and performance (concurrent budget races).

- **Broad exception catch in HTTP error path (CQ-H3):** Bare `except Exception` in `_post_httpx` JSON parsing could mask unexpected errors during error response handling. Security review should verify no sensitive data is swallowed.

- **Shallow immutability on frozen dataclasses (AR-M5 / AR-M6):** `LLMResponse.tool_calls` (mutable list) and `Tool.parameters` (mutable dict) can be mutated post-construction despite `frozen=True`. Security review should assess whether this enables injection of tool calls or parameter tampering. Performance review should assess concurrent access safety.

- **`consensus` ignores budget in `pipe()` (AR-M4):** Budget propagation silently fails for `consensus` steps. Performance review should assess unbounded cost risk when `consensus` is used with high `num_samples`.

- **No retry jitter (from 1a analysis):** `RetryConfig` backoff has no jitter. With `consensus` firing 5+ concurrent requests, synchronized retries cause thundering herd against rate-limited APIs. Performance-critical finding.

- **`MaxIterationsError` never raised (AR-M8):** Patterns silently return rather than signaling iteration exhaustion. Users relying on exception-driven termination will be surprised. Relevant to cost control.

- **Truthiness bug in token fallback (from 1a `_parse_response`):** `input_tokens=0` is treated as falsy and replaced by `prompt_tokens`, producing incorrect cost tracking for cached responses. Financial accuracy impact.

- **Sync wrappers have zero test coverage (from 1a):** Public API surface with no tests is a regression risk for any security or performance fixes.
