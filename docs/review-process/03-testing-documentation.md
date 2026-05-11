# Phase 3: Testing & Documentation Review

**Date:** 2026-04-06
**Sources:** `.full-review/3a-testing.md` (test coverage analysis), `.full-review/3b-documentation.md` (documentation review)

---

## Test Coverage Findings

### Overall Metrics

- **324 tests**, all passing, 10.64s runtime
- **83.29% total coverage** (branch coverage enabled), exceeding the 80% `fail_under` threshold
- **855 statements**, 109 missed; **228 branches**, 32 partial

### CRITICAL

| ID | Finding | Location | Impact |
|----|---------|----------|--------|
| C-TEST-01 | `provider.py` at **58% coverage** — HTTP transport and response parsing largely untested. 84 missed statements, 16 partial branches. Uncovered areas: `complete()` payload construction, `_extract_content()` multipart list handling, `_parse_tool_calls()` validation branches, `_load_json()` error handling, `_post_urllib` 403/404 error mapping. | `provider.py` | The core HTTP client layer has the most complex error paths but the least test coverage. Malformed provider responses and HTTP errors would exercise untested code. |

### HIGH

| ID | Finding | Location |
|----|---------|----------|
| H-TEST-01 | `_extract_content()` multipart content paths (list of dicts with `type: "text"/"output_text"`, nested `text.value`) completely untested — 6 sub-branches uncovered. | `provider.py:400-424` |
| H-TEST-02 | `_parse_tool_calls()` defensive validation branches untested — non-list payloads, non-dict entries, missing function names, JSON string arguments, invalid JSON, non-dict parsed arguments. | `provider.py:427-467` |
| H-TEST-03 | `compose.py` at 84%: `_filter_kwargs` uninspectable-callable fallback (lines 56-57), explicit-parameter-only branch (lines 63-70), and `pipe()` error-cost-accumulation path (lines 121-123) untested. | `compose.py` |

### MEDIUM

| ID | Finding | Location |
|----|---------|----------|
| M-TEST-01 | `cost.py` at 85% — 4 statements uncovered in CostTracker (budget-checking edge cases). | `cost.py:27-29, 57` |
| M-TEST-02 | `_mock.py` at 88% — exception-raising path, empty-responses path, and `last_call` None-return untested. | `_mock.py:65, 68, 85` |
| M-TEST-03 | `json_extraction.py` at 83% — brace-matching fallback, nested depth counting edge case, and array extraction fallback untested (10 statements, 8 branch partials). | `json_extraction.py` |

### LOW

| ID | Finding | Location |
|----|---------|----------|
| L-TEST-01 | No integration tests against real LLM providers despite `@pytest.mark.integration` marker being defined. All 324 tests use MockProvider. | `pyproject.toml:64` |
| L-TEST-02 | Test helper duplication: `_make_response()`, `_make_result()`, `_make_tool_response()` defined independently in 3 test files. | `test_kit.py`, `test_compose.py`, `test_patterns.py` |
| L-TEST-03 | Missing negative type tests for `TokenUsage.__add__` with non-TokenUsage operand. | `types.py` |

### Test Quality Strengths

- Comprehensive pattern coverage with 15+ tests each for consensus, refine_loop, react_loop
- Strong immutability testing — every frozen dataclass has explicit mutation rejection tests
- Dedicated concurrency tests for semaphore limits, cancellation propagation, ExceptionGroup unwrapping
- Security-conscious tests: tool error leak prevention, API key redaction, prompt injection resistance
- Fast suite: 324 tests in 10.64s (well under 5-minute target)
- Public API surface test verifies all 37 symbols in `__all__`

---

## Documentation Findings

### Overall Grade: B+

Strong for a v0.1.0 library. README provides complete onboarding, API reference covers all 37 public symbols, and architecture doc accurately reflects source.

### HIGH

| ID | Finding | Location |
|----|---------|----------|
| DOC-09 | SECURITY.md contains **stale claim** that API keys leak via `Provider.__repr__` — the key is actually masked as `'***'` since the fix at `provider.py:231-236`. | `SECURITY.md:40` |
| DOC-25 | Phase 1/2 review files (`.full-review/01-*.md`, `02-*.md`) contain findings listed as open that have been **resolved in current source** (Kit._record() bypass, LLMResponse truthiness, pydantic in deps, MaxIterationsError unused, API key in repr, no retry jitter). | `.full-review/01-*.md`, `02-*.md` |

### MEDIUM

| ID | Finding | Location |
|----|---------|----------|
| DOC-05 | CONTRIBUTING references `detect-private-key` pre-commit hook without a `.pre-commit-config.yaml` in the repo. | `CONTRIBUTING.md:39` |
| DOC-07 | CHANGELOG documents `PatternResult.metadata` change to `MappingProxyType` (breaking change) but provides no migration guidance. | `CHANGELOG.md:35` |
| DOC-10 | SECURITY.md does not document credential redaction in error messages (`_redact_sensitive()`). | `SECURITY.md` |
| DOC-11 | SECURITY.md prompt injection section is stale — frames XML sandboxing as a recommendation rather than documenting the actual implementation. | `SECURITY.md:44` |
| DOC-16 | Architecture doc implies `RetryConfig` has `slots=True` but source uses only `frozen=True`. | `docs/architecture.md:153` |
| DOC-21 | `_extract_balanced()` in `json_extraction.py` — non-trivial balanced-brace algorithm with no docstring. | `engine/json_extraction.py` |
| DOC-22 | Default evaluator closure in `refine_loop.py` — security-critical XML sandboxing with inline comments but no formal docstring. | `patterns/refine_loop.py:119` |

### LOW

| ID | Finding | Location |
|----|---------|----------|
| DOC-04 | Placeholder `your-org` URLs in README, CONTRIBUTING, SECURITY, pyproject.toml. | Multiple |
| DOC-06 | CONTRIBUTING immutability rule doesn't mention Provider `__post_init__` exception. | `CONTRIBUTING.md:84` |
| DOC-08 | CHANGELOG references internal ticket IDs (P0-2, P2-SEC-06, etc.) without explanation. | `CHANGELOG.md` |
| DOC-12 | SECURITY.md does not mention tool argument validation (`_validate_tool_args`). | `SECURITY.md` |
| DOC-19 | Minor test count inconsistencies across TA-1/TA-5/TA-6 reports. | `docs/test-audit/` |
| DOC-20 | TA-1 finding A2 ("MaxIterationsError never raised") is stale — resolved in current source. | `docs/test-audit/TA-1` |
| DOC-23 | `_TrackedProvider.complete()` docstring is minimal. | `patterns/base.py:157` |
| DOC-24 | Engine/patterns sub-packages lack `__init__.py` module docstrings. | `engine/`, `patterns/` |

### Documentation Strengths

- All 37 public symbols documented in API reference with signatures, parameters, and metadata keys
- README covers setup, quickstart, all 4 patterns, error hierarchy, security, and known limitations
- Architecture doc accurately reflects module map, dependency graph, and data flow
- All public functions have Google-style docstrings with typed Args blocks
- CHANGELOG documents all security fixes, added features, and breaking changes

---

## Cross-Cutting Observations

1. **Provider.py is the common gap**: It has the lowest test coverage (58%) AND its security mitigations (key masking, credential redaction) are inconsistently documented across SECURITY.md vs. README vs. architecture doc. This module should be the top priority for both testing and documentation improvement.

2. **Stale review artifacts**: Both test audit docs and SECURITY.md contain claims that pre-date fixes applied during earlier review phases. A staleness sweep across all documentation is warranted before public release.

3. **Strong foundation despite gaps**: The pattern layer (consensus, refine_loop, react_loop, pipe) has excellent test coverage (97-100%) AND thorough documentation. The gaps are concentrated in the HTTP transport/parsing layer and in documentation maintenance.

---

## Priority Recommendations

### Before Public Release
1. Bring `provider.py` to 80%+ coverage — focus on `_extract_content()`, `_parse_tool_calls()`, `_parse_tool_arguments()`, and HTTP error mapping
2. Update SECURITY.md to reflect current mitigations (key masking, credential redaction, XML sandboxing, tool validation)
3. Replace placeholder `your-org` URLs
4. Add migration guidance for `MappingProxyType` breaking change

### Before v0.2.0
5. Add opt-in integration tests against real OpenAI-compatible endpoints
6. Add docstrings to `_extract_balanced()` and default evaluator closure
7. Resolve `RetryConfig` slots=True discrepancy between docs and source
8. Consolidate duplicate test helpers into conftest.py fixtures
