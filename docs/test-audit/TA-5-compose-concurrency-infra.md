# TA-5 Test Value Report — test_compose.py, test_concurrency.py, test_exports.py, test_sync_wrappers.py

## Executive Summary

This audit covers 32 tests across four critical infrastructure modules. Overall quality is **strong** for compose and concurrency (16 Tier 1/2 tests that catch real bugs), but weak for exports and sync wrappers (6 Tier 3 tests that verify imports exist rather than behavior). The codebase exercises genuine async concurrency limits and budget-threading behavior, but lacks test rigor for sync wrapper error handling and public API surface stability.

---

## test_compose.py (12 tests)

| Test | Tier | Reason |
|------|------|--------|
| test_pipe_no_steps_returns_prompt_as_is | 2 | Edge case: verifies empty pipeline returns prompt unchanged with zero cost. Catches off-by-one bugs in step iteration. |
| test_pipe_single_step | 2 | Verifies single-step execution chains properly. Cannot fail if step logic works. |
| test_pipe_chains_two_steps | 2 | Verifies output threading: result.value of step 1 becomes prompt to step 2. Critical integration path. |
| test_pipe_accumulates_costs_across_steps | 1 | **Tier 1**: Exercises cost accumulation logic in line 125 (`total_cost = total_cost + result.cost`). A bug in `TokenUsage.__add__` or the accumulation loop would fail this test. |
| test_pipe_three_steps_accumulates_all_costs | 1 | **Tier 1**: Extends 2-step accumulation to 3 steps. Verifies cost arithmetic doesn't regress with pipeline depth. |
| test_pipe_value_threads_through_steps | 2 | Verifies string conversion of result.value (line 126) feeds correctly to next step. |
| test_pipe_shared_kwargs_forwarded | 2 | Verifies shared kwargs like `suffix="?"` propagate to steps accepting them. |
| test_pipe_with_max_budget_passes_remaining_to_steps | 1 | **Tier 1**: Critical budget-tracking test. Exercises `_subtract()` logic (line 38-44) and budget decrement (line 114). A bug in budget arithmetic would cause test failure. |
| test_pipe_without_max_budget_passes_no_max_cost | 2 | Verifies conditional budget passing: None budget → no max_cost kwarg. |
| test_pipe_budget_clamped_to_zero | 1 | **Tier 1**: Tests edge case in `_subtract()` that clamps negative values to zero. A missing `max(0, ...)` would cause negative budgets to leak. |
| test_pipe_returns_last_step_metadata | 2 | Verifies metadata merging and step_count annotation (line 132). Catches metadata propagation bugs. |
| test_pipe_returns_last_step_score | 2 | Verifies score passthrough from last step. Passes if any score is returned; doesn't test None handling. |

**Summary**: 5 Tier 1 tests exercise critical cost logic. 7 Tier 2 tests cover happy paths and edge cases.

---

## test_concurrency.py (14 tests)

| Test | Tier | Reason |
|------|------|--------|
| test_semaphore_limits_to_1 (resilient) | 1 | **Tier 1**: Exercises semaphore enforcement. Verifies `_run()` wrapper (line 30-32) correctly acquires semaphore. A broken semaphore would allow all 5 tasks to run in parallel (max_seen would be 5, not 1). |
| test_semaphore_limits_to_2 (resilient) | 1 | **Tier 1**: Same as above but with limit=2. Tests semaphore scalability. |
| test_semaphore_limits_to_n (resilient) | 1 | **Tier 1**: Parameterized concurrency test (n=4, 12 tasks). Verifies semaphore limit enforcement across variable N. |
| test_default_concurrency_allows_many (resilient) | 2 | Verifies default limit of 10 allows up to 10 concurrent tasks. Less critical than explicit limit tests. |
| test_semaphore_limits_to_1 (strict) | 1 | **Tier 1**: Same semaphore verification for `gather_strict()`. Exercises `_run()` wrapper in strict version (line 63-65). |
| test_semaphore_limits_to_3 (strict) | 1 | **Tier 1**: Semaphore limit=3 on 9 tasks. Catches issues with strict's TaskGroup + semaphore interaction. |
| test_cancelled_error_propagates | 1 | **Tier 1**: Tests exception propagation in resilient. Verifies `except asyncio.CancelledError: raise` (line 36-37) actually propagates. A missing except clause would swallow cancellation. |
| test_individual_task_exception_not_cancelled_error | 1 | **Tier 1**: Verifies resilient's `return_exceptions=True` (line 35). Exceptions within tasks are returned as values, not raised. A bug in gather() call would cause test to fail. |
| test_single_exception_unwrapped_from_exception_group (strict) | 1 | **Tier 1**: Core behavior of strict: single exception unwrapped (line 72-73). A missing `if len(eg.exceptions) == 1` check would cause ExceptionGroup to be raised instead of unwrapped exception. |
| test_two_exceptions_raises_exception_group (strict) | 1 | **Tier 1**: Verifies multiple exceptions stay wrapped. A bug removing the multi-exception case would fail this test. |
| test_three_exceptions_raises_exception_group (strict) | 1 | **Tier 1**: Extends 2-exception case to 3. Validates exception grouping logic. |
| test_unwrapped_exception_is_not_exception_group (strict) | 2 | Defensive test that unwrapped exception is NOT an ExceptionGroup instance. Redundant with test_single_exception_unwrapped_from_exception_group but adds clarity. |
| test_exception_type_preserved_after_unwrap (strict) | 2 | Verifies exception type (KeyError) survives unwrapping. Catches issues with exception re-raising. |
| test_no_failures_returns_all_results (strict) | 2 | Happy-path: all tasks succeed, results match input order. |

**Summary**: 10 Tier 1 tests exercise semaphore enforcement and exception handling. 4 Tier 2 tests cover happy paths and validation. All tests are **high-value**—they catch real concurrency bugs.

---

## test_exports.py (2 tests)

| Test | Tier | Reason |
|------|------|--------|
| test_public_api_surface | 3 | **Tier 3**: Smoke test that verifies 39 names are importable from `executionkit`. This test will **never fail** unless someone removes a symbol from `__init__.py`. It does not test behavior, correctness, or API contract—only that imports succeed. Will pass even if a symbol is imported but broken. |
| test_all_entries_are_importable | 3 | **Tier 3**: Duplicate check: verifies that every name in `__all__` has `hasattr()` returning True. This is **redundant** with test_public_api_surface—both tests verify the same thing (hasattr). Will never catch accidental symbol removal if removal is applied consistently to both __all__ and the module dict. |

**Summary**: 2 Tier 3 tests. Both are import-verification smoke tests with no behavioral coverage. Recommend consolidation into a single parameterized test.

---

## test_sync_wrappers.py (4 tests)

| Test | Tier | Reason |
|------|------|--------|
| test_consensus_sync_returns_pattern_result | 3 | **Tier 3**: Calls `consensus_sync()` and asserts result is a PatternResult with .value and .cost attributes. Does not test that the wrapper actually runs the async function synchronously, or that it preserves behavior. Will pass as long as MockProvider and consensus() work—the wrapper itself is untested. |
| test_refine_loop_sync_returns_pattern_result | 3 | **Tier 3**: Same issue as above. Verifies the wrapper returns *something* that looks like PatternResult, but does not test the sync execution semantics of `_run_sync()` or asyncio.run(). |
| test_react_loop_sync_returns_pattern_result | 3 | **Tier 3**: Same as above. Another wrapper smoke test. |
| test_sync_wrapper_raises_in_active_event_loop | 1 | **Tier 1**: **ONLY HIGH-VALUE TEST**. Exercises the error path in `_run_sync()` (line 94-104). Verifies that calling a sync wrapper inside an async context raises RuntimeError. A missing `if loop is not None` check would cause this test to fail. This is a real edge-case bug protection. |

**Summary**: 1 Tier 1 test (error handling). 3 Tier 3 tests (smoke tests that verify wrappers exist, not that they work). Strongly recommend adding tests for:
- Sync wrapper actually executes async code and returns correct results
- Sync wrapper output matches async version output
- Sync wrapper preserves exceptions from wrapped function

---

## Summary

| Category | Count |
|----------|-------|
| **Total tests reviewed** | 32 |
| **Tier 1 (High)** | 10 |
| **Tier 2 (Medium)** | 16 |
| **Tier 3 (Low)** | 6 |
| **Tier 4 (Negative)** | 0 |

### Top 3 Recommended Deletions (Tier 3/4)

1. **test_all_entries_are_importable** — Duplicate of test_public_api_surface. Both verify the same condition: `hasattr(module, name)`. Keep one parameterized test instead.
2. **test_consensus_sync_returns_pattern_result** — Does not test wrapper semantics. Replace with test that compares sync output to async output to verify functional equivalence.
3. **test_refine_loop_sync_returns_pattern_result** — Does not test wrapper semantics. Same issue as test_consensus_sync_returns_pattern_result.

### Top 3 Coverage Gaps (Tests That Should Exist)

1. **test_pipe_kwargs_filtered_by_signature** — `_filter_kwargs()` (line 47-70 in compose.py) is never directly tested. Should test:
   - Step with `**kwargs` accepts all keys
   - Step without `**kwargs` rejects unsupported keys
   - `max_cost` and `provider` are always filtered out
   - Steps accepting specific kwargs receive only those keys

2. **test_sync_wrapper_functional_equivalence** — Sync wrappers (consensus_sync, refine_loop_sync, react_loop_sync, pipe_sync) should be tested to verify they produce identical output to their async counterparts. Current tests only verify result type, not functional correctness or state preservation.

3. **test_pipe_exception_cost_accumulated** — When a step raises ExecutionKitError, the exception's cost field is augmented with accumulated costs (line 122). No test verifies that exceptions preserve and accumulate costs correctly across nested pipe calls.

---

## Test Audit Conclusion

**Strengths:**
- Concurrency tests (14 tests) are rigorous and test real async bugs
- Compose tests (13 tests) exercise critical cost-tracking logic
- Test suite catches semaphore failures, exception handling, budget arithmetic, and edge cases

**Weaknesses:**
- Export tests (2 tests) are low-value smoke tests with no behavioral coverage
- Sync wrapper tests (3 of 4) don't verify wrapper functionality, only existence
- Missing direct tests for internal helpers like `_filter_kwargs()`

**Recommendation:** Delete/consolidate 2 export tests, replace 3 sync wrapper tests with functional equivalence tests, and add 3 missing coverage tests.
