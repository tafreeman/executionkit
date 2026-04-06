# TA-6 Redundancy Report — test_compose.py, test_concurrency.py, test_exports.py, test_sync_wrappers.py

## Executive Summary

**Redundancy Level:** LOW-MODERATE
**Key Finding:** test_compose.py contains parametrizable repetition across concurrency limits that could be collapsed, but the 12 tests cover distinct behavioral paths (no steps, single/multi-step chaining, cost accumulation, budget threading, metadata preservation, scoring). test_concurrency.py has two identical test structures duplicated across gather_resilient and gather_strict; exception unwrapping tests in gather_strict add unique coverage. test_exports.py and test_sync_wrappers.py are minimal and non-redundant.

**Total tests reviewed:** 42 tests
**Highly redundant (safe to delete):** 0 tests
**Parametrize candidates:** 4 clusters
**Estimated line savings:** ~60 lines via parametrization (not deletion)
**Zero-risk deletions (Tier 4):** None identified

---

## Duplicate Coverage Clusters

### Cluster 1: Semaphore Concurrency Limit Tests (Number Sweeping)

**Files:** test_concurrency.py
**Classes:** TestGatherResilientConcurrencyLimit, TestGatherStrictConcurrencyLimit

| Test | Pattern | Issue |
|------|---------|-------|
| test_semaphore_limits_to_1 (resilient) | `max_concurrency=1` → assert `max_seen == 1` | Same structure in gather_strict (lines 83–96) |
| test_semaphore_limits_to_2 (resilient) | `max_concurrency=2` → assert `max_seen <= 2` | Number-sweeping variant |
| test_semaphore_limits_to_n (resilient) | `max_concurrency=4` (parameterized as `n`) → assert `max_seen <= n` | Generalizes the sweep |
| test_default_concurrency_allows_many (resilient) | `max_concurrency` omitted → default=10 | Tests default value |
| test_semaphore_limits_to_1 (strict) | `max_concurrency=1` → assert `max_seen == 1` | Exact duplicate of resilient version |
| test_semaphore_limits_to_3 (strict) | `max_concurrency=3` → assert `max_seen <= 3` | Different value but identical structure |

**Root Cause:** The semaphore limiting logic is identical between `gather_resilient` and `gather_strict` (both create `asyncio.Semaphore` and wrap coros). Testing with concurrency limits {1, 2, 3, 4, 10} is coverage sweeping — all verify the same contract: "semaphore enforces max N concurrent tasks."

**Safe to Parametrize:** YES. Collapse into a single parametrized test fixture:
```python
@pytest.mark.parametrize("max_concurrency,num_tasks", [
    (1, 5, "should allow exactly 1"),
    (2, 8, "should allow up to 2"),
    (3, 9, "should allow up to 3"),
    (4, 12, "should allow up to 4"),
])
async def test_semaphore_limits(max_concurrency, num_tasks):
    # shared test logic
    await gather_resilient([...], max_concurrency=max_concurrency)
    assert max_seen <= max_concurrency
```
Eliminates 4 duplicate tests in gather_strict, keeping 1 parametrized version for both.

---

### Cluster 2: Exception Unwrapping in gather_strict (Variant Testing)

**Files:** test_concurrency.py
**Class:** TestGatherStrictExceptionUnwrapping

| Test | Pattern | Issue |
|------|---------|-------|
| test_single_exception_unwrapped_from_exception_group | 1 failure → unwrap to plain exception | Validates unwrap logic |
| test_two_exceptions_raises_exception_group | 2 failures → keep ExceptionGroup | Validates keep-grouped logic |
| test_three_exceptions_raises_exception_group | 3 failures → keep ExceptionGroup | Repeats test_two logic with different count |
| test_unwrapped_exception_is_not_exception_group | 1 failure (different approach) → verify plain exception | Repeats test_single logic |
| test_exception_type_preserved_after_unwrap | 1 failure → verify type retained | Repeats test_single logic |
| test_no_failures_returns_all_results | 0 failures → all results returned | Happy path (not redundant) |

**Root Cause:** Lines 158–223 test the unwrap threshold (1 → unwrap, 2+ → keep group). Tests 1, 4, 5 all verify "single exception is unwrapped cleanly" with trivial variations (different exception types, different assertion approach). Test 2 and 3 both verify "multiple exceptions stay grouped" — test 3 adds no new information over test 2.

**Safe to Parametrize:** PARTIAL. Collapse unwrap tests into single parametrized test:
```python
@pytest.mark.parametrize("num_failures,expect_unwrap", [
    (1, True),
    (2, False),
    (3, False),
])
async def test_exception_group_unwrap_threshold(num_failures, expect_unwrap):
    # shared logic
```
Eliminates test_three_exceptions (redundant repeat of test_two). Keep test_no_failures as standalone (different behavior path). Optionally consolidate test_unwrapped_exception_is_not_exception_group and test_exception_type_preserved as parametrized variants of test_single_exception_unwrapped.

---

### Cluster 3: pipe() Step-Count Accumulation Tests (Happy Path Variants)

**Files:** test_compose.py

| Test | Pattern | Issue |
|------|---------|-------|
| test_pipe_chains_two_steps | 2 steps → accumulate costs for 2 | N=2 variant |
| test_pipe_accumulates_costs_across_steps | 2 steps → verify input_tokens, output_tokens, llm_calls | Repeats chains_two with added assertions |
| test_pipe_three_steps_accumulates_all_costs | 3 steps → accumulate costs for 3 | N=3 variant |

**Root Cause:** All three test the same behavior (cost accumulation across steps) with N ∈ {2, 3}. test_accumulates_costs_across_steps duplicates test_chains_two logic but verifies individual token fields rather than just llm_calls.

**Assessment:** Low redundancy. test_chains_two and test_accumulates_costs_across_steps are tightly coupled (same inputs, overlapping assertions). test_three_steps provides N=3 as additional coverage point but adds no fundamentally new logic. However, the cost granularity difference (llm_calls vs. per-token breakdown) justifies keeping test_accumulates_costs_across_steps.

**Collapse Candidate:** MINOR. Merge test_chains_two into test_accumulates_costs_across_steps (fewer assertions needed in former). Keep test_three_steps as standalone or parametrize {2, 3} variants. Net: ~5 lines saved.

---

### Cluster 4: Budget Threading Tests (Distinct Behaviors)

**Files:** test_compose.py

| Test | Pattern | Issue |
|------|---------|-------|
| test_pipe_with_max_budget_passes_remaining_to_steps | Budget present → subtract and forward | Core budget logic |
| test_pipe_without_max_budget_passes_no_max_cost | No budget → pass None | Inverse case |
| test_pipe_budget_clamped_to_zero | Budget too small → clamp to zero | Edge case |

**Assessment:** NO REDUNDANCY. These tests cover three orthogonal code paths in the `pipe()` function:
1. **Budget present path** (lines 113–114 in compose.py): _subtract() called, remaining forwarded
2. **No-budget path** (implicit): max_cost not added to kwargs
3. **Underflow path** (lines 40–44 in compose.py): max(0, ...) clamping enforced

Deleting any one would reduce coverage of distinct branches in compose.py.

---

## Parametrize Candidates

| Test Group | Current Count | Collapse To | Estimated Savings |
|------------|--------------|-------------|-------------------|
| Semaphore limits (both gather_* functions) | 6 tests | 1 parametrized + 1 default | ~40 lines |
| Exception unwrap threshold | 5 tests (unwrap-focused) | 1–2 parametrized | ~20 lines |
| pipe() step-count accumulation | 2 closely related | Merge assertions | ~5 lines |

**Total parametrization savings:** ~65 lines (without deleting functionality).

---

## Cross-File Redundancy

### test_sync_wrappers.py vs. test_patterns.py

**Overlap:** Both files test consensus via MockProvider.

| File | Test | Scope |
|------|------|-------|
| test_sync_wrappers.py | test_consensus_sync_returns_pattern_result | Smoke test; verifies sync wrapper works |
| test_patterns.py | test_basic_majority_most_common_wins, test_agreement_ratio_calculation, etc. | Deep consensus algorithm testing |

**Assessment:** NO REDUNDANCY. test_sync_wrappers.py tests the **wrapper mechanism** (async-to-sync bridge), while test_patterns.py tests the **pattern logic** (consensus voting, agreement ratios). They test different layers.

### test_exports.py

**Scope:** Pure API surface coverage (importability, __all__ consistency).

**Assessment:** UNIQUE. No overlaps with other files. Essential for catching import regressions.

---

## Summary

- **Total tests reviewed:** 42 tests (12 compose, 17 concurrency, 2 exports, 4 sync_wrappers, 7 conftest-derived)
- **Highly redundant (safe to delete):** 0 tests
- **Parametrize candidates:** 4 clusters (semaphore sweeps, exception unwrap thresholds, step-count variants, partial)
- **Estimated line savings:** ~65 lines via parametrization (lossless refactoring; no test coverage lost)
- **Zero-risk deletions (Tier 4 from TA-5 cross-reference):** None identified
- **Cross-file redundancy:** None detected

### Recommendations

1. **High Priority:** Parametrize semaphore concurrency tests (Cluster 1). Currently 6 near-identical tests can collapse to 1 parametrized fixture covering {1, 2, 3, 4, 10} with explicit `max_concurrency` and `num_tasks` parameters. Saves ~40 lines.

2. **Medium Priority:** Parametrize exception unwrap threshold tests (Cluster 2). Collapse test_two_exceptions and test_three_exceptions into single `@pytest.mark.parametrize("num_failures,expect_unwrap")` fixture. Saves ~15 lines.

3. **Low Priority:** Merge test_chains_two and test_accumulates_costs_across_steps (Cluster 3). Both test 2-step cost accumulation; keep assertions from latter, remove former. Saves ~5 lines.

4. **No action needed:** Budget threading tests (Cluster 4) and all exports/sync_wrapper tests are non-redundant and should remain.

### Quality Note

All 42 tests are **functionally distinct** in what they verify. No test is a pure copy-paste duplicate (Tier 4). The redundancy identified is at the **parametrization level** — tests that verify the same behavior across a sweep of numeric inputs (concurrency limits, exception counts) can be unified via parametrization without losing coverage.
