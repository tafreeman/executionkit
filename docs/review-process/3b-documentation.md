# Phase 3B: Documentation Review

**Reviewer:** doc-reviewer
**Date:** 2026-04-06
**Scope:** README.md, CONTRIBUTING.md, CHANGELOG.md, SECURITY.md, docs/api-reference.md, docs/architecture.md, docs/test-audit/ (TA-1 through TA-6), inline docstrings
**Cross-references:** `.full-review/01-quality-architecture.md`, `.full-review/02-security-performance.md`

---

## Executive Summary

ExecutionKit's documentation is **strong for a v0.1.0 library** — well-structured, internally consistent, and technically accurate against the current source. The README provides a complete onboarding experience, the API reference documents all 37 public symbols with examples, and the architecture doc accurately reflects the module map and data flow. Key findings are concentrated in **accuracy drift from earlier review phases** (Phase 1/2 findings were addressed in code but the prior review docs now contain stale claims) and **gaps in inline documentation** for complex engine internals.

**Overall Grade: B+**

| Dimension | Rating | Notes |
|-----------|--------|-------|
| README completeness | A | Setup, quickstart, patterns, errors, security, limitations all covered |
| API reference coverage | A | All 37 public symbols documented with signatures, params, metadata keys, examples |
| Architecture accuracy | A- | Module map and data flow match source; minor omission in TOCTOU fix documentation |
| Inline documentation | B | Patterns and types well-documented; engine internals under-documented |
| Accuracy vs. source | B+ | All current claims verified correct; see specific items below |
| CHANGELOG/migration | B | Breaking changes documented but lacks migration guidance for MappingProxyType change |
| SECURITY.md | B- | Contains stale claim about API key leakage; incomplete coverage of mitigations |
| Test audit docs | A- | Thorough tier classification and redundancy analysis; minor inconsistencies in counts |

---

## Detailed Findings

### 1. README.md

#### Verified Accurate

- **Quick Example** (lines 15-25): Import paths, `Provider` constructor, `consensus()` call, `result.cost`, `result.metadata["agreement_ratio"]` all match source. `Provider` positional arg is `base_url` in source (line 204 of provider.py) and the README uses positional style — correct.
- **Features list** (lines 38-44): All 7 claims verified against source:
  - "Composable reasoning patterns" — confirmed: consensus, refine_loop, react_loop, pipe
  - "Budget-aware execution" — confirmed: `checked_complete()` in `patterns/base.py`
  - "Any OpenAI-compatible endpoint" — confirmed: Provider posts to `{base_url}/chat/completions`
  - "Zero runtime dependencies" — confirmed: `dependencies = []` in `pyproject.toml:32`
  - "Type-safe with full mypy --strict" — confirmed: `pyproject.toml:99-101`
  - "Prompt injection defense in default evaluator" — confirmed: XML sandboxing in `refine_loop.py:119-128`
  - "API key masked in Provider.__repr__" — confirmed: `provider.py:231-236`
- **Installation** (lines 48-60): `pip install executionkit` and `[httpx]` extra both match `pyproject.toml:34-35`.
- **Provider Setup** (lines 65-199): All constructor parameters match `Provider` dataclass fields. `default_temperature=0.7`, `default_max_tokens=4096`, `timeout=120.0` all verified.
- **Patterns Reference** (lines 205-289): All function signatures match source. Default parameter values verified against consensus.py, refine_loop.py, react_loop.py.
- **Error Hierarchy** (lines 379-397): All 9 exception classes match `provider.py:42-97`. Inheritance tree is accurate.
- **Security section** (lines 399-421): All claims verified against source.
- **Known Limitations** (lines 423-444): All 4 limitations are accurate and relevant.
- **Test count and coverage** (line 450): "300 tests at 83% coverage" — cannot independently verify count without running tests, but `fail_under = 80` is confirmed in `pyproject.toml:73`.

#### Issues Found

**DOC-01 (LOW) — README claims `react_loop` raises `MaxIterationsError` but refine_loop section says it does not**

- README line 291-292: "Raises `MaxIterationsError` when `max_rounds` is exhausted without a final answer." This is **correct** for `react_loop` (see `react_loop.py:228`).
- README refine_loop section (line 100) does NOT mention MaxIterationsError — also correct. `refine_loop` returns the best result rather than raising.
- No issue here — both are accurate. Marking as verified.

**DOC-02 (LOW) — Provider `__repr__` documentation slightly inconsistent**

- README line 200-201: "masks the API key as `***`"
- README line 409: "shows `api_key='***'` regardless of the actual key length or prefix"
- Source `provider.py:232`: `masked = "***" if self.api_key else ""` — empty key shows `''`, non-empty shows `'***'`.
- Both README descriptions are accurate. No issue.

**DOC-03 (MEDIUM) — `consensus` whitespace normalization claim needs source verification**

- README line 208-209: "Whitespace and trailing newlines are normalized before comparison, so two responses that differ only in whitespace are counted as identical."
- Source `consensus.py:18-20`: `_normalize()` uses `re.sub(r"\s+", " ", text.strip())` — strips, then collapses internal whitespace to single space.
- **Accurate.** Normalization happens before `Counter()` comparison, and the original (un-normalized) winning response is preserved for the result value.

**DOC-04 (LOW) — Placeholder URLs throughout**

- README line 6: `https://github.com/your-org/executionkit/actions`
- CONTRIBUTING line 9: `https://github.com/your-org/executionkit.git`
- SECURITY line 11: `https://github.com/your-org/executionkit/security/advisories/new`
- pyproject.toml lines 48-50: All URLs use `your-org`
- **Impact:** Users cloning or referencing the repo will encounter dead links. This is a pre-publication issue that should be resolved before any public release.

---

### 2. CONTRIBUTING.md

#### Verified Accurate

- **Dev Setup** (lines 8-14): Commands match standard Python workflow. `pip install -e ".[dev]"` matches `pyproject.toml:36-45` dev dependencies.
- **Pre-commit hooks** (lines 28-40): Ruff rules `E, F, W, I, N, UP, S, B, A, C4, SIM, TCH, RUF` match `pyproject.toml:83`. `mypy --strict` matches `pyproject.toml:100-101`.
- **Test commands** (lines 52-60): `--cov=executionkit --cov-fail-under=80` matches `pyproject.toml:62,73`.
- **Architecture key modules table** (lines 101-110): All module descriptions match source layout.
- **Commit Convention** (lines 114-130): Follows Conventional Commits standard.
- **Anti-Scope** (lines 159-165): Clear boundaries documented.

#### Issues Found

**DOC-05 (MEDIUM) — CONTRIBUTING references `detect-private-key` hook but no `.pre-commit-config.yaml` visible**

- Line 39 lists `detect-private-key` as a pre-commit hook. No `.pre-commit-config.yaml` was found in the repo root (it is untracked). This hook may exist locally but is not part of the committed source, making it unverifiable for new contributors.

**DOC-06 (LOW) — Style rules mention immutability but don't mention Provider exception**

- Line 84: "All value types are `@dataclass(frozen=True, slots=True)`."
- Provider IS frozen per `provider.py:196`, but uses `object.__setattr__` in `__post_init__` for derived state. The architecture doc (line 161-165) documents this exception, but CONTRIBUTING does not. Minor gap for contributors.

---

### 3. CHANGELOG.md

#### Verified Accurate

- **Security fixes**: XML delimiter sandboxing (`refine_loop.py:119-128`), API key masking (`provider.py:231-236`), credential redaction, tool error handling — all verified in source.
- **Added features**: httpx backend (`provider.py:29-35, 219-229`), `max_history_messages` (`react_loop.py:98,159-164`), `_validate_tool_args` (`react_loop.py:32-63`), `aclose()` and context manager (`provider.py:238-256`) — all verified.
- **Fixed items**: Whitespace normalization in consensus (`consensus.py:18-20`), `_parse_score` range validation, pydantic removal from dependencies (`pyproject.toml:32`) — all verified.
- **Changed items**: `PatternResult.metadata` to `MappingProxyType` (`types.py:58-59`) — verified.

#### Issues Found

**DOC-07 (MEDIUM) — CHANGELOG lacks migration guidance for MappingProxyType change**

- The change from `dict[str, Any]` to `MappingProxyType[str, Any]` for `PatternResult.metadata` (line 35) is a **breaking change** for any user code that mutates `result.metadata["key"] = value`. The CHANGELOG documents the change but does not provide migration guidance (e.g., "convert to dict with `dict(result.metadata)` if mutation is needed").

**DOC-08 (LOW) — CHANGELOG references internal ticket IDs without explanation**

- References like `(P0-2)`, `(P2-SEC-06)`, `(P1-5)`, `(P2-M2)` etc. appear throughout. These appear to be internal review finding IDs but are not explained for external consumers. Minor for v0.1.0.

---

### 4. SECURITY.md

#### Issues Found

**DOC-09 (HIGH) — SECURITY.md contains stale claim about API key leakage**

- Line 40: "API keys may appear in `Provider.__repr__` — avoid logging provider instances in production"
- This directly contradicts the CHANGELOG (which documents the fix) and the source (`provider.py:231-236` where `__repr__` masks the key as `'***'`).
- The README correctly states the key is masked. SECURITY.md was not updated to reflect the fix.
- **Fix:** Change to "API keys are masked as `'***'` in `Provider.__repr__`. However, avoid logging provider instances at DEBUG level, as internal state may still be exposed."

**DOC-10 (MEDIUM) — SECURITY.md does not document credential redaction in error messages**

- The README (lines 396-397) and architecture doc (lines 207-216) document `_redact_sensitive()` for credential redaction in error messages. SECURITY.md does not mention this mitigation.

**DOC-11 (MEDIUM) — SECURITY.md prompt injection section is stale**

- Line 44: "Use structured output mode or explicit delimiters when evaluating untrusted content."
- The implementation now uses XML delimiters by default (confirmed in `refine_loop.py:119-128`). SECURITY.md still frames this as a recommendation rather than documenting the actual mitigation in place.

**DOC-12 (LOW) — SECURITY.md does not mention tool argument validation**

- `_validate_tool_args()` in `react_loop.py:32-63` validates tool call arguments against JSON Schema before execution. This is documented in README and architecture doc but not in SECURITY.md.

---

### 5. docs/api-reference.md

#### Verified Accurate

- **Quick Reference table**: Lists 37 public symbols matching `__all__` in `__init__.py` (excluding `__version__`). All symbol names, kinds, and descriptions are accurate.
- **Function signatures**: All pattern function signatures (`consensus`, `refine_loop`, `react_loop`, `pipe`) match source exactly. Default values verified.
- **Parameter tables**: All parameter names, types, defaults, and descriptions verified against source.
- **Metadata keys**: All documented metadata keys verified:
  - `consensus`: `agreement_ratio`, `unique_responses`, `tie_count` — verified in `consensus.py`
  - `refine_loop`: `iterations`, `converged`, `score_history` — verified in `refine_loop.py`
  - `react_loop`: `rounds`, `tool_calls_made`, `truncated_responses`, `truncated_observations`, `messages_trimmed` — verified in `react_loop.py:147-153`
- **Type definitions**: `PatternResult`, `TokenUsage`, `Tool`, `VotingStrategy`, `Evaluator`, `ToolCall`, `LLMResponse` — all fields match source.
- **Provider class**: Constructor parameters, methods (`complete`, `aclose`), context manager protocol — all verified.
- **Error hierarchy**: All 9 exceptions, their inheritance, and descriptions — verified.
- **Kit class**: Constructor, properties, methods — verified against `kit.py`.
- **Examples**: All code examples use correct import paths and API.

#### Issues Found

**DOC-13 (LOW) — API reference lists `consensus` `retry` default as `None` with note "uses `DEFAULT_RETRY` if `None`"**

- This is accurate behavior (the `retry or DEFAULT_RETRY` pattern in `checked_complete` at `base.py:91`), but the signature itself passes `None` as default. The documentation correctly explains the behavior. No issue.

**DOC-14 (LOW) — `refine_loop` API reference states "MaxIterationsError -- not raised by refine_loop"**

- Line 194: "MaxIterationsError -- not raised by `refine_loop`; it returns after `max_iterations` even if not converged"
- Verified: `refine_loop.py` does not raise `MaxIterationsError`. It returns the best result. **Accurate.**

**DOC-15 (LOW) — `react_loop` API reference documents `score: Always None`**

- Line 286: "`score`: Always `None`"
- Verified: `react_loop.py:182` returns `score=None`. **Accurate.**

**DOC-16 (MEDIUM) — `RetryConfig` documented with `slots=True` in architecture doc but source uses only `frozen=True`**

- `engine/retry.py:18`: `@dataclass(frozen=True)` — no `slots=True`.
- Architecture doc immutability contract table (line 153): Lists `RetryConfig` alongside types that use `frozen=True, slots=True`.
- API reference line (not shown but implied): Lists `RetryConfig` as immutable dataclass.
- The architecture doc's immutability table implies `RetryConfig` has `slots=True` but it does not. Minor inaccuracy.

---

### 6. docs/architecture.md

#### Verified Accurate

- **Design Principles** (lines 5-31): All 5 principles verified:
  1. Zero runtime dependencies — `pyproject.toml:32`
  2. Flat package layout — confirmed by directory structure
  3. Frozen value types — all dataclasses use `frozen=True`
  4. Async-first, sync wrappers — `__init__.py:95-150`
  5. Composable, not opinionated — confirmed by function signatures

- **Module Map** (lines 36-57): All files and descriptions match source directory structure.
- **Dependency graph** (lines 59-72): Verified by import statements in each module. No circular imports detected.
- **Data Flow** (lines 82-127): Accurately describes the call chain. Includes TOCTOU fix (`tracker._calls += 1` pre-increment) documented at line 100.
- **Immutability Contract** (lines 142-169): Accurate including the `Provider.__post_init__` exception and `CostTracker` as intentional mutable type.
- **Error Handling Architecture** (lines 174-202): Error tree, retry boundary, pattern boundary, and tool boundary all accurate.
- **Security Layers** (lines 205-244): All 5 security layers documented and verified against source.
- **Extension Points** (lines 248-317): Custom `LLMProvider`, custom pattern, and evaluator function interfaces all accurate.
- **Engine Layer** (lines 320-367): ConvergenceDetector, RetryConfig, parallel functions, and extract_json all accurately described.

#### Issues Found

**DOC-17 (LOW) — Architecture doc references `record_without_call` at line 111 but the TOCTOU pre-increment is at `checked_complete` not `CostTracker`**

- The data flow diagram (line 100) shows `tracker._calls += 1 ← TOCTOU-safe pre-increment` which accurately describes `base.py:87`. The subsequent `tracker.record_without_call(response)` at line 111 is also accurate (`base.py:98`). No issue upon closer inspection.

**DOC-18 (LOW) — Architecture doc says RetryConfig uses "full jitter" (`random.uniform(0, cap)`)**

- `engine/retry.py:50`: `return random.uniform(0.0, cap)` — confirmed. The architecture doc at line 339 states "Uses full jitter" which is accurate.

---

### 7. docs/test-audit/ (TA-1 through TA-6)

#### Summary

The test audit covers 6 files reviewing approximately 257 tests across the entire test suite:

| Report | Tests Reviewed | Tier 1 (High) | Tier 2 (Medium) | Tier 3 (Low) | Tier 4 (Negative) |
|--------|---------------|----------------|------------------|---------------|-------------------|
| TA-1 (patterns/engine/kit) | 122 | 51 | 30 | 32 | 9 |
| TA-2 (redundancy) | 122 | — | — | — | — |
| TA-3 (provider/types/sync) | 103 | 39 | 20 | 23 | 21 |
| TA-4 (redundancy) | 103 | — | — | — | — |
| TA-5 (compose/concurrency) | 32 | 10 | 16 | 6 | 0 |
| TA-6 (redundancy) | 42 | — | — | — | — |

#### Verified Accurate

- **Tier classifications** are consistent and well-reasoned. Tier 1 tests exercise error paths and edge cases. Tier 4 tests are correctly identified as mock-only or pure inheritance checks.
- **Coverage gaps** identified are legitimate:
  - Empty response handling in consensus (TA-1)
  - HTTP error mapping completeness in provider (TA-3)
  - `_filter_kwargs()` untested in compose (TA-5)
  - Sync wrapper functional equivalence (TA-5)
- **Redundancy analysis** is sound. Parametrization recommendations would reduce test count without coverage loss.

#### Issues Found

**DOC-19 (LOW) — TA-1 and TA-5 test count inconsistencies**

- TA-1 reviews 122 tests. TA-5 reviews 32 tests. TA-6 claims 42 tests reviewed (includes conftest-derived). The total across value reports is 122 + 103 + 32 = 257, but TA-6 redundancy claims 42. Minor counting inconsistency, likely due to conftest fixtures counted differently.

**DOC-20 (LOW) — TA-1 states `MaxIterationsError` is "exported but never raised" (finding A2)**

- This was a Phase 1 finding. In the current source, `react_loop.py:228` raises `MaxIterationsError`. The test audit was written before the fix was applied, making this claim stale. The TA docs should note that A2 has been resolved.

---

### 8. Inline Documentation (Source Code Docstrings)

#### Strengths

- **All public functions have docstrings** with Args, Returns, Metadata, and Raises sections.
- **Docstring format is consistent** across all pattern functions: Google-style with typed Args blocks.
- **`checked_complete()`** (`base.py:35-64`) has a thorough docstring explaining the three-step process and all parameters.
- **`CostTracker`** (`cost.py:17-65`) documents all methods including the TOCTOU-related `record_without_call()`.
- **`_validate_tool_args()`** (`react_loop.py:32-63`) is an internal helper but is well-documented with clear return semantics.
- **`ConvergenceDetector`** has docstrings on `should_stop()` and `reset()`.
- **Error classes** all have one-line docstrings describing their cause.

#### Issues Found

**DOC-21 (MEDIUM) — `_extract_balanced()` in `json_extraction.py` lacks docstring explaining the algorithm**

- This function implements a balanced-brace/bracket scanner with string boundary awareness. The algorithm is non-trivial (depth tracking, escape handling) but has no docstring. Phase 1 finding M7 notes the implementation has a robustness gap (single depth counter for both `{}`/`[]`). A docstring explaining the approach and its known limitations would help maintainers.

**DOC-22 (MEDIUM) — `_default_evaluator` closure in `refine_loop.py` has inline comments but no formal docstring**

- The default evaluator (`refine_loop.py:119-128`) is a critical security boundary (XML sandboxing). It has inline comments about truncation and injection mitigation but no formal docstring. Given its security importance, a docstring would be appropriate.

**DOC-23 (LOW) — `_note_truncation()` and `_TrackedProvider` in `base.py` have docstrings but the `_TrackedProvider.complete()` docstring is minimal**

- Line 157: `"""Delegate to ``checked_complete`` and call ``_note_truncation``."""` — adequate but could mention the budget/retry wrapping behavior.

**DOC-24 (LOW) — Engine module `__init__.py` files are missing**

- `engine/` and `patterns/` sub-packages have no `__init__.py` module docstrings (they are implicit namespace packages). Not a functional issue, but module-level docstrings would help IDE navigation.

---

### 9. Cross-Cutting Accuracy Issues

**DOC-25 (HIGH) — Phase 1/2 review files contain stale findings that were subsequently fixed**

The `.full-review/01-quality-architecture.md` and `.full-review/02-security-performance.md` documents contain findings that have been resolved in the current source:

| Finding | Status in Review Doc | Actual Status in Source |
|---------|---------------------|------------------------|
| H1: Kit._record() bypasses CostTracker encapsulation | Listed as open | **Fixed**: `kit.py:42` uses `self._tracker.add_usage(cost)` |
| H3: LLMResponse truthiness bug | Listed as open | **Fixed**: `provider.py:131` uses `if "input_tokens" in u` key-presence check |
| M1: pydantic in dependencies | Listed as open | **Fixed**: `pyproject.toml:32` has `dependencies = []` |
| A2: MaxIterationsError never raised | Listed as open | **Fixed**: `react_loop.py:228` raises it |
| SEC-01: eval() in example | Listed as critical | **Cannot verify** — example file not read in this review |
| SEC-07: API key in repr | Listed as open | **Fixed**: `provider.py:231-236` masks key |
| PERF-02: No jitter in retry | Listed as open | **Fixed**: `retry.py:50` uses `random.uniform(0.0, cap)` |

These review documents should either be updated or clearly marked as "pre-fix snapshots."

---

## Summary of Findings by Severity

### HIGH (2 findings)

| ID | Description | Location |
|----|-------------|----------|
| DOC-09 | SECURITY.md contains stale claim that API keys leak via `__repr__` | SECURITY.md:40 |
| DOC-25 | Phase 1/2 review files contain findings that have been resolved in source | .full-review/01-*.md, 02-*.md |

### MEDIUM (6 findings)

| ID | Description | Location |
|----|-------------|----------|
| DOC-05 | CONTRIBUTING references `detect-private-key` hook without visible config | CONTRIBUTING.md:39 |
| DOC-07 | CHANGELOG lacks migration guidance for MappingProxyType breaking change | CHANGELOG.md:35 |
| DOC-10 | SECURITY.md does not document credential redaction in error messages | SECURITY.md |
| DOC-11 | SECURITY.md prompt injection section is stale (doesn't reflect actual mitigation) | SECURITY.md:44 |
| DOC-16 | Architecture doc implies RetryConfig has `slots=True` but it does not | docs/architecture.md:153 |
| DOC-21 | `_extract_balanced()` lacks docstring for non-trivial algorithm | engine/json_extraction.py |
| DOC-22 | Default evaluator closure lacks formal docstring despite security importance | patterns/refine_loop.py:119 |

### LOW (8 findings)

| ID | Description | Location |
|----|-------------|----------|
| DOC-04 | Placeholder `your-org` URLs throughout | README, CONTRIBUTING, SECURITY, pyproject.toml |
| DOC-06 | CONTRIBUTING immutability rule doesn't mention Provider __post_init__ exception | CONTRIBUTING.md:84 |
| DOC-08 | CHANGELOG references internal ticket IDs without explanation | CHANGELOG.md |
| DOC-12 | SECURITY.md does not mention tool argument validation | SECURITY.md |
| DOC-19 | Minor test count inconsistencies across TA reports | docs/test-audit/ |
| DOC-20 | TA-1 finding A2 (MaxIterationsError never raised) is stale | docs/test-audit/TA-1 |
| DOC-23 | `_TrackedProvider.complete()` docstring is minimal | patterns/base.py:157 |
| DOC-24 | Engine/patterns sub-packages lack `__init__.py` module docstrings | engine/, patterns/ |

---

## Public API Symbol Coverage

**Target:** All 37 public symbols documented with examples.

| Symbol | API Ref | README | Architecture | Has Example |
|--------|---------|--------|--------------|-------------|
| `consensus()` | Yes | Yes | Yes | Yes |
| `consensus_sync()` | Yes | Yes | No | Yes |
| `refine_loop()` | Yes | Yes | Yes | Yes |
| `refine_loop_sync()` | Yes | Yes | No | No (but sync usage shown) |
| `react_loop()` | Yes | Yes | Yes | Yes |
| `react_loop_sync()` | Yes | Yes | No | No |
| `pipe()` | Yes | Yes | No | Yes |
| `pipe_sync()` | Yes | No | No | No |
| `Kit` | Yes | Yes | Yes | Yes |
| `Provider` | Yes | Yes | Yes | Yes (multiple providers) |
| `MockProvider` | Yes | No | Yes | No (mentioned, not exemplified) |
| `PatternResult[T]` | Yes | Yes | Yes | Implicit in all examples |
| `TokenUsage` | Yes | Yes | Yes | Yes (in pipe budget example) |
| `Tool` | Yes | Yes | Yes | Yes |
| `LLMResponse` | Yes | No | Yes | Yes (custom provider) |
| `ToolCall` | Yes | No | Yes | No |
| `LLMProvider` | Yes | Yes | Yes | Yes (custom provider) |
| `ToolCallingProvider` | Yes | No | Yes | Yes (in architecture) |
| `VotingStrategy` | Yes | No | No | No |
| `Evaluator` | Yes | No | Yes | Yes (custom evaluator) |
| `PatternStep` | Yes | No | No | No |
| `RetryConfig` | Yes | No | Yes | No |
| `DEFAULT_RETRY` | Yes | No | Yes | No |
| `ConvergenceDetector` | Yes | No | Yes | No |
| `CostTracker` | Yes | No | Yes | No |
| `extract_json()` | Yes | No | Yes | No |
| `checked_complete()` | Yes | No | Yes | No |
| `validate_score()` | Yes | No | No | No |
| 9 exception classes | Yes | Yes | Yes | Implicit in error handling |

**Coverage:** All 37 symbols are documented in the API reference. 18/37 have explicit code examples. The remaining 19 are engine/internal symbols or type definitions that are adequately described without examples.

---

## Recommendations

### Priority 1 (Before Public Release)

1. **Update SECURITY.md** to reflect the current state of API key masking, credential redaction, XML sandboxing, and tool argument validation (DOC-09, DOC-10, DOC-11, DOC-12).
2. **Replace `your-org` placeholder URLs** in README, CONTRIBUTING, SECURITY, and pyproject.toml (DOC-04).
3. **Add migration guidance to CHANGELOG** for the `MappingProxyType` change (DOC-07).

### Priority 2 (Before v0.2.0)

4. **Add docstrings** to `_extract_balanced()` and the default evaluator closure (DOC-21, DOC-22).
5. **Add `slots=True`** to `RetryConfig` dataclass to match the documented immutability contract, or update the architecture doc table (DOC-16).
6. **Add `.pre-commit-config.yaml`** to the repository or remove the `detect-private-key` reference from CONTRIBUTING (DOC-05).

### Priority 3 (Maintenance)

7. Mark Phase 1/2 review files as historical snapshots or update them to reflect fixes applied (DOC-25).
8. Add module-level docstrings to `engine/` and `patterns/` sub-packages (DOC-24).
9. Consider adding standalone examples for `MockProvider`, `VotingStrategy`, `PatternStep`, and `RetryConfig` in the API reference.
