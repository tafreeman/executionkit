# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run unit tests (fast, no API keys needed)
pytest -m "not integration"

# Run all tests with coverage (must stay ≥80%)
pytest --cov=executionkit --cov-fail-under=80

# Run a single test
pytest tests/test_patterns.py::test_name -v

# Run integration tests (requires real API keys)
OPENAI_API_KEY=sk-... pytest -m integration

# Lint, format, type-check, security scan
ruff check .
ruff format .
mypy --strict executionkit/
bandit -r executionkit/
```

Pre-commit hooks run ruff, mypy, detect-private-key, and check-merge-conflict automatically on every commit.

## Architecture

ExecutionKit is a minimal library for LLM reasoning patterns — it fills the gap between raw chat calls and full orchestration stacks. Three core patterns: **consensus** (parallel sampling + voting), **refine_loop** (iterative improvement), **react_loop** (tool calling). Zero runtime dependencies (stdlib only; `httpx` optional via `[httpx]` extra).

### Module responsibilities

| Module | Role |
|--------|------|
| `errors.py` | 9-class exception hierarchy (`ExecutionKitError` → `LLMError`, `PatternError` subtrees); extracted from `provider.py` (F-06) |
| `provider.py` | `LLMProvider` protocol, `Provider` HTTP client, `LLMResponse`; re-exports error classes from `errors.py` for backwards compatibility; `_classify_http_error()` is the single HTTP status→exception mapping point shared by both backends (F-02) |
| `types.py` | Frozen value types: `TokenUsage`, `PatternResult[T]`, `Tool`, `VotingStrategy`, `Evaluator` |
| `cost.py` | `CostTracker` — mutable accumulator with two-phase accounting (`reserve_call` + `record_without_call`) |
| `patterns/base.py` | `checked_complete()` — shared budget guard + retry entry point; `_check_budget()` helper uses `getattr()` field loop replacing per-field if-chains (F-05/F-08); `_TrackedProvider.supports_tools` delegates to wrapped provider via `getattr` instead of hardcoding `Literal[True]` (F-04) |
| `patterns/consensus.py` | Parallel sampling, majority/unanimous voting, agreement metadata |
| `patterns/refine_loop.py` | Iterative improvement with `ConvergenceDetector`; default evaluator uses XML sandboxing |
| `patterns/react_loop.py` | Think-act-observe loop; validates tool args against JSON Schema; caps context via `max_history_messages` |
| `engine/` | `ConvergenceDetector`, `RetryConfig`/`with_retry`, `gather_strict`/`gather_resilient`, `extract_json`, `user_message` |
| `compose.py` | `pipe()` — chains patterns threading `result.value` as next prompt; shared budget optional |
| `kit.py` | `Kit` — optional session facade holding provider + cumulative `CostTracker` |
| `_mock.py` | `MockProvider` — test double used throughout test suite |

### Key design invariants

**Immutability** — all value types are `@dataclass(frozen=True, slots=True)`. `__post_init__` wraps mutable fields in `MappingProxyType`. Never mutate; return new objects.

**Two-phase cost accounting** — `reserve_call()` pre-increments the call counter before `await` (TOCTOU-safe for concurrent patterns); `record_without_call(response)` adds token counts after success.

**Budget guards** — `checked_complete()` in `patterns/base.py` checks token/call budget before every LLM call and raises `BudgetExhaustedError` (with accumulated cost snapshot) if exceeded. The internal `_check_budget()` helper iterates over field names using `getattr()` rather than repeating an if-block per field (F-05/F-08).

**Centralised HTTP error mapping** — `_classify_http_error()` in `provider.py` is the single function that converts HTTP status codes to the appropriate error subclass. Both the `_post_httpx` and `_post_urllib` backends call it, eliminating the duplicated mapping logic that previously existed in each (F-02).

**Structural typing** — `LLMProvider` and `ToolCallingProvider` are `@runtime_checkable` protocols, not base classes. Any object matching the interface works.

**Async-first** — all patterns are `async`; sync wrappers (`consensus_sync`, `refine_loop_sync`, etc.) live in `__init__.py` and raise `RuntimeError` if called inside a running event loop.

**Prompt injection defense** — `refine_loop`'s default evaluator wraps model output in `<response_to_rate>` XML delimiters before sending to the evaluator LLM.

### Data flow (refine_loop example)

```
refine_loop(provider, prompt)
  → CostTracker() + ConvergenceDetector()
  → checked_complete()  [budget guard → reserve_call → with_retry → provider.complete]
  → tracker.record_without_call(response)
  → Evaluator(text, provider)  [optional; may re-enter checked_complete]
  → ConvergenceDetector.should_stop(score)
  → PatternResult(value, score, cost=tracker.to_usage(), metadata=MappingProxyType(...))
```

### Testing conventions

- Use `MockProvider` from `executionkit._mock` in unit tests — never make real HTTP calls outside `@pytest.mark.integration` tests.
- Fixtures (`mock_provider`, `multi_response_provider`, `make_llm_response`) live in `conftest.py`.
- Coverage must stay above 80% (`fail_under = 80` in `pyproject.toml`).

### Version

Stored in `executionkit/__init__.py`; hatchling extracts it automatically. Follows Semantic Versioning with Conventional Commits (`feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`).
