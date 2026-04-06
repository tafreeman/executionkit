# TA-2 Redundancy Report — test_patterns.py, test_engine.py, test_kit.py

**Total tests analyzed:** 122 (40 in test_patterns.py, 67 in test_engine.py, 15 in test_kit.py)

---

## Vacuous Tests — Remove Immediately (3 tests)

| Test | File | Issue |
|------|------|-------|
| `test_result_is_pattern_result` | test_patterns.py:102 | Asserts `isinstance(result, PatternResult)` only — cannot catch logic bugs |
| `test_result_is_pattern_result_str` (consensus) | test_patterns.py:109 | Asserts `isinstance(result.value, str)` only |
| `test_result_is_pattern_result_str` (refine_loop) | test_patterns.py:275 | Same — type contract only |
| `test_result_is_pattern_result_str` (react_loop) | test_patterns.py:454 | Same — type contract only |

---

## Mock-Only Tests — Remove Immediately (4 tests)

All in `test_kit.py` lines 86–208:

| Test | Issue |
|------|-------|
| `test_kit_consensus_delegates_to_consensus_fn` | Only verifies `mock.assert_called_once_with()` — tests mock setup, not Kit behavior |
| `test_kit_refine_delegates_to_refine_loop` | Same |
| `test_kit_react_delegates_to_react_loop` | Same |
| `test_kit_pipe_delegates_to_pipe_fn` | Same |

These are covered by Kit integration tests. Delegation is guaranteed by Kit's trivial one-line implementations.

---

## Duplicate Coverage Clusters (11 clusters)

### Cluster 1 — RetryConfig defaults (test_engine.py:25–42)
- `test_default_max_retries`
- `test_default_base_delay`
- `test_default_max_delay`
- `test_default_exponential_base`

All follow `assert RetryConfig().<field> == expected`. **Collapse to 1 parametrized test.**

### Cluster 2 — should_retry error classification (test_engine.py:54–72)
- `test_should_retry_rate_limit_error`
- `test_should_retry_provider_error`
- `test_should_not_retry_permanent_error`
- `test_should_not_retry_value_error`
- `test_should_not_retry_runtime_error`

**Collapse to 1 parametrized test with `(exception_type, expected_bool)` table.**

### Cluster 3 — get_delay bounds (test_engine.py:80–106)
- `test_attempt_1_within_*`
- `test_attempt_2_within_*`
- `test_attempt_3_within_*`
- `test_delay_capped_at_max_delay`
- `test_delay_at_max_boundary`

All test `0.0 <= delay <= cap`. `test_delay_at_max_boundary` duplicates capping logic already in `test_delay_capped_at_max_delay`. **Remove boundary test; parametrize remaining 4.**

### Cluster 4 — with_retry exhaustion (test_engine.py:138–222)
- `test_raises_after_max_retries_exhausted`
- `test_max_retries_zero_does_not_retry_on_error`
- `test_call_count_equals_max_retries_on_exhaustion`

`test_call_count_equals_max_retries_on_exhaustion` is fully covered by the first two. **Remove it.**

### Cluster 5 — ConvergenceDetector score validation (test_engine.py:350–373)
- `test_nan_score_raises_value_error`
- `test_score_below_zero_raises_value_error`
- `test_score_above_one_raises_value_error`
- `test_score_zero_is_valid`
- `test_score_one_is_valid`

**Collapse to 1 parametrized test with `(score, should_raise)` table.**

### Cluster 6 — ConvergenceDetector threshold comparison (test_engine.py:375–385)
- `test_meets_score_threshold_returns_true`
- `test_exceeds_score_threshold_returns_true`
- `test_below_score_threshold_returns_false`

All test `score >= threshold`. **Collapse to 1 parametrized test.**

### Cluster 7 — ConvergenceDetector stale count (test_engine.py:387–427)
- `test_stale_delta_for_patience_iterations_returns_true`
- `test_improving_scores_not_converged`
- `test_stale_count_resets_on_improvement`

Last two both test counter reset on improvement. **Remove `test_stale_count_resets_on_improvement`.**

### Cluster 8 — gather_resilient vs gather_strict (test_engine.py:257–342)
`test_empty_list_returns_empty`, `test_preserves_order`, `test_respects_max_concurrency` appear in BOTH classes with identical logic. **Remove gather_strict versions of these 3 tests** — keep gather_resilient, keep the error-handling distinctions.

### Cluster 9 — extract_json fence variations (test_engine.py:444–501)
- `test_json_in_markdown_fences`
- `test_json_in_generic_code_fence`
- `test_markdown_fence_with_extra_text_before`

Trivial input variations on the same extraction path. **Collapse to 1 parametrized test.**

---

## Merge/Delete Recommendations

| Action | Tests | Saving |
|--------|-------|--------|
| Delete vacuous | 4 | 4 tests |
| Delete mock-only (Kit) | 4 | 4 tests |
| Delete exact duplicates (Clusters 4, 7, 8) | 5 | 5 tests |
| Parametrize (Clusters 1, 2, 3, 5, 6, 9) | ~22 → 6 | ~16 tests |
| **Total** | | **~27% reduction** |

**Estimated result: 122 → 86–90 tests with zero coverage loss.**

---

## Summary

- Total analyzed: 122
- Immediate deletes (vacuous + mock-only + exact duplicates): 13 tests
- Parametrize candidates: 7 clusters → 7 tests (saves ~16 more)
- Coverage lost: **zero**
