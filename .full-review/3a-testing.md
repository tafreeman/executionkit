# Phase 3A: Test Coverage Analysis

**Date:** 2026-04-06
**Scope:** executionkit test suite — all files under `tests/`
**Coverage Tool:** pytest-cov (branch coverage enabled)
**Total Coverage:** 83.29% (324 tests, all passing, 10.64s runtime)

---

## Overall Coverage Summary

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|-------|------|--------|--------|-------|
| `__init__.py` | 34 | 0 | 2 | 0 | 100% |
| `_mock.py` | 35 | 3 | 6 | 2 | 88% |
| `compose.py` | 46 | 7 | 10 | 2 | 84% |
| `cost.py` | 27 | 4 | 0 | 0 | 85% |
| `engine/__init__.py` | 6 | 0 | 0 | 0 | 100% |
| `engine/convergence.py` | 27 | 0 | 10 | 0 | 100% |
| `engine/json_extraction.py` | 71 | 10 | 34 | 8 | 83% |
| `engine/parallel.py` | 27 | 0 | 4 | 0 | 100% |
| `engine/retry.py` | 32 | 0 | 4 | 0 | 100% |
| `kit.py` | 35 | 0 | 2 | 0 | 100% |
| `patterns/__init__.py` | 5 | 0 | 0 | 0 | 100% |
| `patterns/base.py` | 47 | 1 | 12 | 1 | 97% |
| `patterns/consensus.py` | 37 | 0 | 6 | 1 | 98% |
| `patterns/react_loop.py` | 81 | 0 | 38 | 2 | 98% |
| `patterns/refine_loop.py` | 60 | 0 | 16 | 0 | 100% |
| `provider.py` | 249 | 84 | 84 | 16 | 58% |
| `types.py` | 36 | 0 | 0 | 0 | 100% |
| **TOTAL** | **855** | **109** | **228** | **32** | **83%** |

---

## Severity-Rated Findings

### CRITICAL

#### C-TEST-01: `provider.py` at 58% coverage — well below the 80% threshold
- **Location:** `executionkit/provider.py`
- **Details:** The `Provider` class is the core HTTP client layer. 84 statements and 16 branch partials are uncovered. The uncovered code includes:
  - Lines 268-282: The `complete()` method payload construction (temperature, max_tokens, tools forwarding)
  - Lines 306-316: `_post_httpx` response parsing branches for non-JSON error responses
  - Lines 350-362, 367, 380: `_post_urllib` error handling — 403/404 permanent error mapping, retry-after header parsing with missing headers
  - Lines 393-424: `_extract_content()` — multipart content list handling (list of dicts with `type: "text"/"output_text"`, nested `text.value` objects, non-dict list items)
  - Lines 430-467: `_parse_tool_calls()` and `_parse_tool_arguments()` — validation branches (non-list tool_calls, non-dict entries, missing function.name, non-string/non-dict arguments)
  - Lines 472-478: `_load_json()` — UnicodeDecodeError branch, non-dict JSON payload
- **Impact:** The HTTP transport and response parsing layer has the most complex error paths in the codebase. These untested branches include production-critical error mapping (HTTP status code -> exception type) and defensive parsing for malformed LLM responses.
- **Recommendation:** Add integration-style tests using monkeypatched httpx/urllib backends to cover:
  1. `complete()` with explicit temperature, max_tokens, and tools arguments
  2. `_extract_content()` with list-of-dicts content format (OpenAI/Anthropic multipart responses)
  3. `_parse_tool_calls()` with malformed payloads (non-list, non-dict entries, missing fields)
  4. `_load_json()` with non-UTF-8 bytes and non-dict JSON arrays
  5. `_post_urllib` with 403 and 404 status codes

### HIGH

#### H-TEST-01: `_extract_content()` multipart content paths untested
- **Location:** `executionkit/provider.py:400-424`
- **Details:** The `_extract_content()` helper handles 4 content formats: `None`, `str`, `list`, and fallback `str()`. The list branch has 6 sub-paths (plain string items, dict items with `type: "text"`, dict items with `type: "output_text"`, nested `text.value` dicts, items with `.value` attribute, non-dict items). None of the list sub-paths are tested.
- **Impact:** Any provider returning multipart content (e.g., Anthropic Messages API, OpenAI with content arrays) would exercise untested code paths.

#### H-TEST-02: `_parse_tool_calls()` validation branches untested
- **Location:** `executionkit/provider.py:427-467`
- **Details:** While `react_loop` tests exercise the happy path (valid tool calls from MockProvider), the defensive validation in `_parse_tool_calls()` is not covered:
  - `raw_tool_calls` is not a list -> raises `ProviderError`
  - Individual tool call is not a dict -> raises `ProviderError`
  - `function` field is not a dict -> raises `ProviderError`
  - `name` is missing or empty -> raises `ProviderError`
  - `arguments` is a JSON string (needs parsing) vs. already a dict
  - `arguments` is an invalid JSON string -> raises `ProviderError`
  - Parsed arguments is not a dict -> raises `ProviderError`
- **Impact:** Malformed tool call responses from real providers (truncated JSON, wrong types) would hit untested error paths.

#### H-TEST-03: `compose.py` error propagation and `_filter_kwargs` edge cases
- **Location:** `executionkit/compose.py:56-57, 63-70, 121-123`
- **Details:** Missing coverage includes:
  - Line 56-57: `_filter_kwargs` when `inspect.signature()` raises `ValueError`/`TypeError` (uninspectable callables)
  - Lines 63-70: `_filter_kwargs` when step has no `**kwargs` — the explicit-parameter-only branch
  - Lines 121-123: `pipe()` error handling — when a step raises `ExecutionKitError`, cost should be accumulated onto the exception
- **Impact:** The `_filter_kwargs` uninspectable-callable fallback and the error-cost-accumulation path in `pipe()` are production code paths that run when chaining patterns that raise.

### MEDIUM

#### M-TEST-01: `cost.py` — 85% coverage, 4 statements missing
- **Location:** `executionkit/cost.py:27-29, 57`
- **Details:** The `CostTracker` class has untested paths:
  - Lines 27-29: Likely a property or method that's unused by current patterns
  - Line 57: Likely a budget-checking edge case
- **Impact:** Minor — `CostTracker` is an internal utility, and its primary paths are exercised indirectly through pattern tests.

#### M-TEST-02: `_mock.py` — 88% coverage, 3 statements missing
- **Location:** `executionkit/_mock.py:65, 68, 85`
- **Details:** Uncovered lines in MockProvider:
  - Line 65: The `exception` raising path — when `self.exception is not None`
  - Line 68: Empty responses returning `LLMResponse(content="")`
  - Line 85: `last_call` returning `None` when no calls made
- **Impact:** Low — these are test infrastructure, not production code. However, the `exception` path is the mechanism for testing error flows, so it should be exercised.

#### M-TEST-03: `json_extraction.py` — 83% coverage, 10 statements + 8 branch partials
- **Location:** `executionkit/engine/json_extraction.py:43-65, 96, 110-115, 132-138`
- **Details:** Several branches in the JSON extraction logic are untested:
  - Lines 43-65: Brace-matching fallback for JSON embedded in text where the regex fails
  - Line 96: Edge case in nested brace counting
  - Lines 110-115: Handling of JSON with trailing content after valid parse
  - Lines 132-138: Array extraction fallback path
- **Impact:** The `extract_json()` function is used by `refine_loop` for parsing evaluator output. Untested branches handle adversarial or malformed text that could silently fail.

### LOW

#### L-TEST-01: No E2E/integration tests against real LLM providers
- **Details:** All 324 tests use `MockProvider`. There are markers defined for `integration` and `slow` tests (`pyproject.toml:63-65`), but no tests carry these markers. While mock-based testing is appropriate for CI, the absence of any integration tests means the HTTP transport layer (`Provider.complete()`, `_post_httpx`, `_post_urllib`) has never been validated end-to-end.
- **Recommendation:** Add opt-in integration tests (gated by `@pytest.mark.integration` and an env-var check) that call a real OpenAI-compatible endpoint (e.g., local Ollama) to validate the full request/response cycle.

#### L-TEST-02: Test organization could benefit from fixtures consolidation
- **Details:** Several test files define their own `_make_response()`, `_make_result()`, and `_make_tool_response()` helpers independently (`test_kit.py:20-44`, `test_compose.py:21-27`, `test_patterns.py:413-432`). These could be consolidated into `conftest.py` fixtures to reduce duplication.
- **Impact:** Maintenance burden, not a correctness issue.

#### L-TEST-03: Missing negative tests for `TokenUsage.__add__` with non-TokenUsage operand
- **Details:** `TokenUsage.__add__` is tested with valid operands but not with invalid types (e.g., `TokenUsage() + 5`). If `__add__` doesn't return `NotImplemented` for unsupported types, it could produce confusing errors.

---

## Test Quality Assessment

### Strengths

1. **Comprehensive pattern coverage**: consensus, refine_loop, and react_loop each have 15+ tests covering happy paths, edge cases, error conditions, and security scenarios (prompt injection, secret leaking).

2. **Strong immutability testing**: Every frozen dataclass (`TokenUsage`, `PatternResult`, `LLMResponse`, `ToolCall`, `Tool`, `RetryConfig`) has explicit freeze tests verifying `FrozenInstanceError` or `AttributeError` on mutation attempts.

3. **Concurrency testing**: Dedicated `test_concurrency.py` validates semaphore limits for `gather_resilient` and `gather_strict` with multiple concurrency levels, cancellation propagation, and `ExceptionGroup` unwrapping.

4. **Security-conscious tests**: `test_tool_error_leaks_only_type` (line 1138) verifies tool exceptions don't leak sensitive data to the LLM. `test_format_http_error_redacts_key_fragment` verifies API key redaction. `test_default_evaluator_resists_injection` tests prompt injection resistance.

5. **Sync wrapper coverage**: Both `test_sync_and_parse.py` and `test_sync_wrappers.py` cover the synchronous API surface including the "raises in async context" guard.

6. **Fast test suite**: 324 tests in 10.64 seconds is well under the 5-minute target.

7. **Public API surface test**: `test_exports.py` verifies all 37 public names in `__all__` are importable, catching accidental regressions.

### Weaknesses

1. **Provider module is the coverage hole**: At 58%, `provider.py` drags down overall coverage. It contains 29% of all source statements but accounts for 77% of all missed statements.

2. **No integration tests exist despite markers being defined**: The test infrastructure supports `@pytest.mark.integration` but no test uses it.

3. **Response parsing is mock-bypassed**: `MockProvider` returns pre-constructed `LLMResponse` objects, meaning `_parse_response()`, `_extract_content()`, `_parse_tool_calls()`, and `_parse_tool_arguments()` are never exercised through the normal MockProvider flow. Only a few direct tests in `test_provider.py` exercise `_parse_response()` — and those only cover the simplest cases.

4. **Branch coverage is 86%** (228 branches, 32 partial): Most partial branches are in `provider.py` and `json_extraction.py`. The branch coverage configuration correctly includes `branch = true` in pyproject.toml.

---

## Coverage Configuration Review

The `pyproject.toml` coverage configuration is well-structured:
- `fail_under = 80` enforces the minimum threshold
- `branch = true` enables branch coverage (not just line coverage)
- `skip_empty = true` excludes `__init__.py` files with only imports
- `exclude_lines` correctly exempts `TYPE_CHECKING`, `NotImplementedError`, and `__name__` blocks
- Test markers for `integration` and `slow` are defined but unused

---

## Summary

| Severity | Count | Key Finding |
|----------|-------|-------------|
| CRITICAL | 1 | `provider.py` at 58% — HTTP transport and response parsing largely untested |
| HIGH | 3 | Multipart content parsing, tool call validation, compose error propagation untested |
| MEDIUM | 3 | Minor gaps in cost tracker, mock provider, and JSON extraction |
| LOW | 3 | No integration tests, test helper duplication, missing negative type tests |

**Overall assessment:** The test suite is well-structured and thorough for the pattern layer (consensus, refine, react, pipe), type system, and engine utilities. The critical gap is `provider.py` at 58% coverage, which contains the HTTP transport layer and response parsing. This module handles the most complex real-world error conditions (malformed responses, HTTP errors, multipart content) and should be the top priority for additional test coverage.
