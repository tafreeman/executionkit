# Phase 4: Best Practices & Standards

**Date:** 2026-04-06
**Sources:** Phase 4A (Framework & Language Best Practices), Phase 4B (CI/CD & DevOps)

---

## Combined Severity Summary

| Severity | Framework & Language (4A) | CI/CD & DevOps (4B) | Total |
|----------|--------------------------|---------------------|-------|
| Critical | 0 | 0 | **0** |
| High     | 2 | 3 | **5** |
| Medium   | 8 | 6 | **14** |
| Low      | 9 | 5 | **14** |
| **Total** | **19** | **14** | **33** |

---

## Framework & Language Findings

### High Severity

| ID | Finding | File(s) |
|----|---------|---------|
| BP-DC4 | `LLMResponse` frozen dataclass has mutable `list`/`dict` fields -- consumers can mutate `tool_calls` and `usage` without raising `FrozenInstanceError`, violating the immutability contract | `provider.py` |
| BP-PR1 | `_TrackedProvider.supports_tools` unconditionally `True` regardless of wrapped provider capability -- falsely satisfies `ToolCallingProvider` protocol | `patterns/base.py` |

### Medium Severity

| ID | Finding | File(s) |
|----|---------|---------|
| BP-DC1 | `ConvergenceDetector` missing `slots=True` -- inconsistent with codebase convention, loses memory/performance benefits | `engine/convergence.py` |
| BP-DC2 | `MockProvider` and `_CallRecord` missing `slots=True` -- compounds across 324+ test instantiations | `_mock.py` |
| BP-DC3 | `ConvergenceDetector.__eq__` compares runtime state (`_scores`, `_stale_count`) -- two identically configured detectors compare unequal after use | `engine/convergence.py` |
| BP-DC5 | `Tool.parameters` is a mutable `dict` on a frozen dataclass -- can be mutated between registration and invocation | `types.py` |
| BP-AS1 | `asyncio.to_thread` in `_post_urllib` has no cancellation propagation -- orphaned threads pile up under high cancellation rates, risking thread pool exhaustion | `provider.py` |
| BP-TY1 | Sync wrappers use `cast()` instead of a typed `_run_sync` with `TypeVar` -- bypasses type checking on return values | `__init__.py` |
| BP-TY4 | `checked_complete` directly accesses `tracker._calls` (private field) for TOCTOU-safe pre-increment -- needs `reserve_call()`/`release_call()` API | `patterns/base.py`, `cost.py` |
| BP-PT2 | Pre-commit mypy hook version mismatch (`v1.10.0` vs `>=1.18`) and missing `additional_dependencies` -- runs without project type stubs | `.pre-commit-config.yaml` |

### Low Severity

| ID | Finding | File(s) |
|----|---------|---------|
| BP-PY1 | `isinstance(x, (dict, list))` should use Python 3.10+ union syntax `dict | list` (4 instances) | `json_extraction.py` |
| BP-PY2 | HTTP status dispatch could use `match` statement for readability | `provider.py` |
| BP-AS2 | Dead `except CancelledError: raise` in `gather_resilient` -- `asyncio.gather(return_exceptions=True)` never raises it | `parallel.py` |
| BP-TY2 | `pipe_sync` accepts `*steps: Any` instead of `*steps: PatternStep` -- loses type contract | `__init__.py` |
| BP-TY3 | `gather_resilient` return type `Any | BaseException` is redundant (`Any` already encompasses all types) | `parallel.py` |
| BP-PT1 | Pre-commit ruff version stale (`v0.4.0` vs `>=0.14.0`) -- local and CI lint results diverge | `.pre-commit-config.yaml` |
| BP-PT6 | `[project.urls]` uses placeholder `your-org` URL -- will 404 on PyPI | `pyproject.toml` |
| BP-PT7 | Missing `py.typed` PEP 561 marker file -- downstream type checkers cannot recognize typed package | `executionkit/` |
| BP-DP2 | `import logging` inside exception handler -- unconventional; should be module-level | `react_loop.py` |

### Positive Observations (Framework & Language)

- Consistent `frozen=True, slots=True` on all cross-boundary value types
- PEP 544 structural protocols for `LLMProvider` and `ToolCallingProvider` with correct `@runtime_checkable`
- `from __future__ import annotations` in every module (PEP 563)
- `StrEnum` for `VotingStrategy` -- enables both type-safe comparison and string acceptance
- `asyncio.TaskGroup` in `gather_strict` with correct `ExceptionGroup` unwrapping
- Full jitter in retry backoff (`random.uniform(0.0, cap)`)
- AST-based safe math evaluator replacing prior `eval()` sandbox
- Comprehensive Ruff rule selection (13 categories)
- `_redact_sensitive` in HTTP error paths for credential sanitization
- Zero runtime dependencies with optional `httpx` extra

---

## CI/CD & DevOps Findings

### High Severity

| ID | Finding | File(s) |
|----|---------|---------|
| CD-H1 | Publish workflow has no CI gate -- can release to PyPI with failing tests, lint errors, or security scan failures | `publish.yml` |
| CD-H2 | No version-tag consistency verification -- git tag `v0.2.0` could publish `executionkit-0.1.0`, causing permanent version divergence | `publish.yml`, `pyproject.toml` |
| CD-H3 | Pre-commit hook versions severely outdated (ruff `v0.4.0` vs CI `>=0.14.0`, mypy `v1.10.0` vs `>=1.18`) -- local and CI results diverge | `.pre-commit-config.yaml` |

### Medium Severity

| ID | Finding | File(s) |
|----|---------|---------|
| CD-M1 | No dependency vulnerability scanning (pip-audit) in CI pipeline -- dev and optional deps unchecked for CVEs | `ci.yml` |
| CD-M2 | No coverage artifact upload or trend tracking -- coverage regressions within threshold go unnoticed | `ci.yml` |
| CD-M3 | Security scan (Bandit) runs independently with unclear branch protection requirements -- failures may not block merges | `ci.yml` |
| CD-M4 | No changelog verification in release process -- releases ship without documented changes | `publish.yml` |
| CD-M5 | Build matrix missing macOS -- `asyncio` event loop differences (`kqueue` vs `epoll`) could cause platform-specific bugs | `ci.yml` |
| CD-M6 | Editable install (`-e`) in CI masks packaging issues -- broken wheel configuration passes CI but fails for end users | `ci.yml` |

### Low Severity

| ID | Finding | File(s) |
|----|---------|---------|
| CD-L1 | No `py.typed` marker file (PEP 561) -- downstream mypy users get no type checking | `pyproject.toml` |
| CD-L2 | Placeholder `your-org` GitHub URLs in `pyproject.toml` -- could be squatted on PyPI | `pyproject.toml` |
| CD-L3 | No pip dependency caching in CI -- 6-job matrix reinstalls from scratch every run | `ci.yml` |
| CD-L4 | Publish workflow uses Python 3.11 without documented rationale | `publish.yml` |
| CD-L5 | No branch protection settings documented in CONTRIBUTING.md | `CONTRIBUTING.md` |

### Positive Observations (CI/CD & DevOps)

- OIDC Trusted Publishing for PyPI -- no long-lived API tokens stored as secrets
- Dependabot configured for both `pip` and `github-actions` ecosystems
- Comprehensive 2 OS x 3 Python version build matrix with `fail-fast: false`
- Coverage enforcement in CI matching `pyproject.toml` configuration (`--cov-fail-under=80`)
- Separate Bandit SAST job for visibility
- Build/publish artifact separation in release workflow
- Environment-scoped publishing enabling GitHub protection rules
- Pre-commit hooks covering linting, formatting, type checking, and secret detection
- Zero runtime dependencies -- no transitive vulnerability surface
- Bandit suppression rules documented with inline justifications

---

## Deduplicated Cross-Cutting Findings

The following findings appear in both 4A and 4B reviews, counted once:

| Finding | 4A ID | 4B ID | Consolidated |
|---------|-------|-------|-------------|
| Missing `py.typed` marker file | BP-PT7 | CD-L1 | Count once as **High priority packaging fix** |
| Placeholder `your-org` URLs in pyproject.toml | BP-PT6 | CD-L2 | Count once as **Pre-publish blocker** |
| Pre-commit hook version drift (ruff, mypy) | BP-PT1, BP-PT2 | CD-H3 | Count once as **High -- tooling consistency** |

**Unique findings after deduplication: 30** (33 total minus 3 duplicates)

---

## Consolidated Recommendations by Priority

### Immediate (before first PyPI publish)

1. **CD-H1** -- Add CI gate to publish workflow (prevents publishing broken releases)
2. **CD-H2** -- Add version-tag consistency check (prevents version divergence)
3. **BP-DC4** -- Enforce true immutability on `LLMResponse` (coerce `list` -> `tuple`, `dict` -> `MappingProxyType`)
4. **BP-PR1** -- Fix `_TrackedProvider.supports_tools` to delegate to wrapped provider
5. **BP-PT6/CD-L2** -- Replace placeholder URLs (prevents URL squatting on PyPI)
6. **BP-PT7/CD-L1** -- Add `py.typed` marker file (PEP 561 compliance)

### Short-term (next 2-3 sprints)

7. **CD-H3/BP-PT1/BP-PT2** -- Update all pre-commit hook versions to match CI
8. **CD-M1** -- Add `pip-audit` dependency vulnerability scanning to CI
9. **CD-M6** -- Switch to non-editable install in CI
10. **BP-TY4** -- Add `reserve_call()`/`release_call()` to `CostTracker`
11. **BP-DC1/BP-DC2** -- Add `slots=True` to `ConvergenceDetector`, `MockProvider`, `_CallRecord`
12. **BP-DC3** -- Exclude runtime state from `ConvergenceDetector.__eq__` via `compare=False`
13. **BP-DC5** -- Wrap `Tool.parameters` in `MappingProxyType`
14. **BP-TY1** -- Type `_run_sync` with `TypeVar` to eliminate `cast()` calls
15. **BP-AS1** -- Document thread-leak risk in `_post_urllib`; reduce default timeout
16. **CD-M3** -- Document required branch protection status checks
17. **CD-M2** -- Add coverage artifact upload; consider Codecov integration

### Backlog (when touching these files)

18. **BP-PY1** -- Update `isinstance` calls to union syntax
19. **BP-PY2** -- Convert HTTP status dispatch to `match` statement
20. **BP-AS2** -- Remove dead `except CancelledError` guard
21. **BP-TY2** -- Fix `pipe_sync` type signature
22. **BP-TY3** -- Simplify `gather_resilient` return type
23. **BP-DP2** -- Move `import logging` to module level
24. **CD-M4** -- Add changelog verification to release process
25. **CD-M5** -- Add macOS to build matrix
26. **CD-L3** -- Add pip caching to CI
27. **CD-L4** -- Document Python version choice for publish build
28. **CD-L5** -- Document branch protection settings

---

## Previously Resolved Issues

16 findings from prior reviews have been verified as fixed in the current codebase, including: phantom pydantic dependency, retry jitter, TOCTOU budget race, token truthiness bug, CostTracker encapsulation (partial), Provider freezing, consensus whitespace normalization, eval() sandbox, MaxIterationsError, pyproject metadata, Provider repr masking, pytest-asyncio pinning, ruff version pin, Kit.__init__ typing, tool argument validation, and react_loop message trimming.
