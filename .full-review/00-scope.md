# Review Scope

## Target

**ExecutionKit source library** — `executionkit/` package and supporting files.

ExecutionKit is a minimal Python library (v0.1.0-alpha) for composable LLM reasoning patterns targeting OpenAI-compatible APIs. Has 8 committed development cycles, 324 passing tests at 83.29% coverage, optional httpx transport, immutable `Provider` dataclass.

## Files Under Review

### Root package (`executionkit/`)
- `__init__.py` — public exports, `__version__`, sync wrappers
- `_mock.py` — `MockProvider` scriptable test double
- `compose.py` — `pipe()` composition and `PatternStep` protocol
- `cost.py` — `CostTracker` mutable accumulator
- `kit.py` — `Kit` session defaults wrapper
- `provider.py` — `Provider` (frozen dataclass, httpx transport), error hierarchy (9 classes), protocols
- `types.py` — `TokenUsage`, `PatternResult[T]`, `Tool`, `VotingStrategy`, `Evaluator`

### Engine (`executionkit/engine/`)
- `convergence.py` — `ConvergenceDetector` (delta+patience, fixed delta=0.0 semantics)
- `json_extraction.py` — balanced-brace JSON fallback
- `parallel.py` — `gather_resilient` / `gather_strict` with asyncio.Semaphore + TaskGroup
- `retry.py` — `RetryConfig`, `with_retry` exponential backoff

### Patterns (`executionkit/patterns/`)
- `base.py` — `checked_complete`, `validate_score`, `_TrackedProvider`
- `consensus.py` — majority/unanimous voting pattern
- `refine_loop.py` — iterative refinement with evaluator feedback
- `react_loop.py` — tool-calling ReAct execution loop

### Tests (`tests/`)
- `conftest.py`, `test_engine.py`, `test_types.py`, `test_provider.py`
- `test_compose.py`, `test_kit.py`, `test_patterns.py`, `test_exports.py`
- `test_concurrency.py`, `test_sync_wrappers.py`, `test_sync_and_parse.py`

### Configuration
- `pyproject.toml` — build, `[httpx]` optional extra, pinned ruff `>=0.14.0,<0.15`
- `.github/workflows/ci.yml` — CI matrix (Ubuntu + Windows, Python 3.11/3.12/3.13)
- `.github/workflows/publish.yml` — PyPI trusted publishing

### Reference Documentation (context only)
- `docs/api-reference.md` — 1142-line API reference
- `docs/architecture.md` — module map, data-flow, immutability contract
- `docs/test-audit/` — TA-1 through TA-6 audit reports
- `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`

## Out of Scope
- `node_modules/`, `package.json` (unrelated JS scaffolding)
- `planning/` (archived planning docs)
- `coverage.json`, `evaluation_result.md` (artifacts)

## Flags
- Security Focus: no
- Performance Critical: no
- Strict Mode: no
- Framework: Python 3.11+ / asyncio / httpx (optional)

## Review Phases
1. Code Quality & Architecture
2. Security & Performance
3. Testing & Documentation
4. Best Practices & Standards
5. Consolidated Report
