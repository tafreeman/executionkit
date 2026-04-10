# ExecutionKit v2 Roadmap

> Single source of truth for what ships in v0.2.
> Organised into four tiers: correctness fixes first, then new features,
> then provider/engine maturity, then ecosystem polish.
> Each item has a rationale, scope, acceptance criteria, and effort estimate.
>
> Status update (2026-04-10): `retry_after` handling, observation truncation
> enforcement, bool-safe tool-arg validation, README count cleanup, and a
> proper task-runner Makefile have already shipped. Treat this document as a
> roadmap input for remaining work, not as a changelog.

---

## Principles

1. **Fix before feature.** Ship correctness and safety patches before adding
   surface area.
2. **Stay sharp.** ExecutionKit is a pattern library, not a framework. Every new
   public symbol must earn its place. Reject dashboards, graph runtimes,
   provider-matrix sprawl, and multi-agent orchestration.
3. **Zero required deps.** New capabilities use stdlib. Optional extras (httpx,
   Pydantic) stay optional.
4. **Type-safe.** Every public API passes `mypy --strict`. No untyped `Any`
   without justification.
5. **Budget-aware.** New patterns and provider features must participate in
   `CostTracker` / `TokenUsage` accounting.

---

## Tier 1 — Correctness & Safety

> These are bugs or semantic gaps in shipped v0.1 code.
> **All Tier 1 items block the v0.2 release.**

---

### 1.1 · `llm_calls` under-counts retries

| | |
|---|---|
| **File** | `engine/retry.py`, `patterns/base.py` |
| **Problem** | `checked_complete()` reserves exactly one call slot before entering `with_retry()`. If the provider call fails and is retried, each retry is a real wire call but is never counted. `llm_calls` therefore under-reports actual API usage. |
| **Impact** | Cost accounting is understated. `llm_calls` budgets do not cap real wire calls. |
| **Fix** | Option A: increment `_calls` inside `with_retry` per attempt (requires passing the tracker). Option B: rename `llm_calls` to "logical completions" and document the distinction, then add a separate `wire_calls` counter. Prefer Option A — users expect `llm_calls` to mean actual HTTP calls. |
| **Acceptance** | `result.cost.llm_calls` equals the number of HTTP requests dispatched, including retries. Budget enforcement stops retries when the limit is reached. Tests cover 0-retry, 1-retry, and budget-exhaustion-mid-retry scenarios. |
| **Effort** | Small (2–4 hr) |

---

### 1.2 · `retry_after` from 429 responses is ignored

| | |
|---|---|
| **File** | `engine/retry.py`, `provider.py` |
| **Problem** | `RateLimitError` carries `retry_after` (parsed from the provider's `Retry-After` header). But `with_retry()` ignores it and always uses jittered exponential backoff from `RetryConfig`. |
| **Impact** | Retries may fire before the provider allows, causing additional 429s and unnecessary churn. |
| **Fix** | In `with_retry()`, when the caught exception is a `RateLimitError`, use `max(config.get_delay(attempt), exc.retry_after)` as the sleep duration. |
| **Acceptance** | A `RateLimitError` with `retry_after=5.0` causes the retry loop to sleep at least 5 s. Unit test mocks the provider to return 429 with a known `Retry-After` and asserts sleep duration. |
| **Effort** | Small (1–2 hr) |

---

### 1.3 · `_trim_messages` can split tool-call / tool-result pairs

| | |
|---|---|
| **File** | `patterns/react_loop.py` |
| **Problem** | `_trim_messages()` keeps `messages[0]` plus the most recent N−1 entries. This can split an assistant tool-call message from its following `tool` result message, producing an invalid chat history that causes provider errors. |
| **Impact** | Intermittent failures when `max_history_messages` is used in long tool loops. |
| **Fix** | Replace naive slicing with block-aware trimming: identify assistant + tool-result groups and never split them. Always keep the first message (original prompt). |
| **Acceptance** | No trimmed history ever contains an assistant message with `tool_calls` without its corresponding `tool` role messages. Add a test with 3+ tool rounds and `max_history_messages=5` that verifies pairing. |
| **Effort** | Small–Medium (2–4 hr) |

---

### 1.4 · Observation truncation exceeds `max_observation_chars`

| | |
|---|---|
| **File** | `patterns/react_loop.py` |
| **Problem** | `_truncate()` returns `text[:max_chars] + "\n[truncated]"`, which is `max_chars + 12` characters — longer than the configured limit. |
| **Impact** | Token/context growth is larger than requested. The contract with `max_observation_chars` is violated. |
| **Fix** | Reserve space for the marker: `text[:max_chars - len(marker)] + marker`, or document that the limit is approximate and the marker is additive. Prefer the former. |
| **Acceptance** | `len(_truncate(long_text, 100))` is `<= 100` for any input. |
| **Effort** | Trivial (30 min) |

---

### 1.5 · `bool` passes `"integer"` / `"number"` tool-arg validation

| | |
|---|---|
| **File** | `patterns/react_loop.py` |
| **Problem** | `_JSON_SCHEMA_TYPE_MAP` maps `"integer"` to `int` and `"number"` to `(int, float)`. Because Python `bool` is a subclass of `int`, `True` / `False` silently pass integer and number checks. |
| **Impact** | Tool argument validation is weaker than users expect. |
| **Fix** | Add an explicit `bool` exclusion: `isinstance(value, expected) and not isinstance(value, bool)` when the schema type is `"integer"` or `"number"`. |
| **Acceptance** | `_validate_tool_args({"properties": {"n": {"type": "integer"}}}, {"n": True})` returns an error string. |
| **Effort** | Trivial (30 min) |

---

### 1.6 · Missing input validation on public numeric parameters

| | |
|---|---|
| **File** | Multiple patterns |
| **Problem** | `consensus()` validates `num_samples >= 1`, but other functions do not validate their numeric params: `react_loop` accepts `max_rounds=0` or `max_observation_chars=-1`; `refine_loop` accepts `target_score=2.0` or `patience=-1`; `gather_*` accept `max_concurrency=0`. |
| **Impact** | Bad inputs silently deadlock, produce empty results, or have undefined behavior. |
| **Fix** | Add `ValueError` guards at the top of each public function for: `max_rounds >= 1`, `max_observation_chars >= 1`, `tool_timeout > 0` (when not None), `max_concurrency >= 1`, `target_score` in [0.0, 1.0], `patience >= 1`, `delta_threshold >= 0.0`, `max_iterations >= 0`. |
| **Acceptance** | Each invalid value raises `ValueError` with a descriptive message. Unit tests for each boundary. |
| **Effort** | Small (2–3 hr) |

---

## Tier 2 — New Patterns & Capabilities

> Features that align with ExecutionKit's scope as a composable pattern library.
> No framework creep — each feature is a single function or a small protocol
> extension.

---

### 2.1 · `structured()` — JSON / structured output pattern

| | |
|---|---|
| **Rationale** | The most common LLM workflow after free-text: "answer in JSON, validate, retry/repair". ExecutionKit already ships `extract_json()` and has retry/budget primitives — this composes them into a first-class pattern. |
| **API sketch** | `async def structured(provider, prompt, *, validator=None, max_retries=3, ...) -> PatternResult[dict \| list]` |
| **Behaviour** | 1) Prompt with JSON instruction. 2) Parse with `extract_json()`. 3) If `validator` callback is provided, call it; on failure, build a repair prompt including the error and retry. 4) Budget-aware via `checked_complete`. |
| **Metadata** | `parse_attempts`, `repair_attempts`, `validated` (bool). |
| **File** | New `patterns/structured.py` |
| **Acceptance** | Works with both raw JSON and markdown-fenced JSON from the LLM. Validator failures trigger repair prompts. Budget exhaustion raises `BudgetExhaustedError`. Tests use `MockProvider` with deliberately broken JSON on first attempt. |
| **Effort** | Medium (4–6 hr) |

---

### 2.2 · Streaming provider API

| | |
|---|---|
| **Rationale** | README already lists lack of streaming as a known limitation. Users building real-time UIs expect incremental token delivery. |
| **API sketch** | `StreamEvent` dataclass (delta, finish_reason, usage). `Provider.stream_complete(...) -> AsyncIterator[StreamEvent]`. Helper `collect_stream(stream) -> LLMResponse`. |
| **Scope** | Provider-level only for v0.2. Patterns remain batch. An `async for` consumer can wrap any pattern's LLM call in the future. |
| **Protocol** | New `StreamingProvider(Protocol)` with `stream_complete`. |
| **File** | Extend `provider.py`; new `engine/streaming.py` for `collect_stream`. |
| **Acceptance** | `async for event in provider.stream_complete(messages): ...` yields `StreamEvent` objects. `collect_stream()` returns an `LLMResponse` equivalent to a batch call. Works with OpenAI-compatible SSE endpoints. httpx backend required (stdlib urllib does not support streaming reads well). |
| **Effort** | Medium–Large (6–10 hr) |

---

### 2.3 · `consensus()` with rationale & normalization hooks

| | |
|---|---|
| **Rationale** | Users want "majority vote + explanation" and domain-specific answer normalization. Current `consensus()` returns only the winning text and metadata. |
| **API additions** | New optional params: `normalize: Callable[[str], str] | None = None` for domain-specific answer canonicalization (applied before vote counting, after whitespace collapse). `include_rationale: bool = False` triggers a cheap follow-up call asking the LLM to summarize why the winning cluster won. |
| **Metadata additions** | `rationale` (str, when requested), `winning_votes` (int). |
| **File** | `patterns/consensus.py` |
| **Acceptance** | Custom normalizer changes vote grouping. Rationale is a concise string explaining the majority. Cost includes the rationale call. |
| **Effort** | Small–Medium (3–5 hr) |

---

### 2.4 · Concurrent tool execution in `react_loop`

| | |
|---|---|
| **Rationale** | When the LLM returns multiple tool calls in one round, they are currently executed sequentially. For I/O-bound tools (HTTP, DB) this is unnecessarily slow. |
| **API addition** | New param `parallel_tools: bool = False`. When `True`, tool calls within a single round are dispatched via `gather_resilient()` with the existing concurrency limiter. |
| **File** | `patterns/react_loop.py` |
| **Acceptance** | Two independent tool calls in one round complete in ~1× the slowest tool's time, not 2×. Failed tools still return error strings without crashing the loop. Sequential remains the default. |
| **Effort** | Small–Medium (3–5 hr) |

---

## Tier 3 — Provider & Engine Maturity

> Improvements to the HTTP layer, retry, and budget infrastructure that
> make ExecutionKit more reliable in production but don't add new patterns.

---

### 3.1 · Per-request headers and extra body fields

| | |
|---|---|
| **Rationale** | Some OpenAI-compatible providers require custom headers (e.g. `X-Api-Version`) or extra body fields (e.g. `stream_options`). |
| **API additions** | `Provider(..., default_headers=None, default_query=None)`. `complete(..., extra_headers=None, extra_body=None)`. Protocol updated. |
| **File** | `provider.py` |
| **Acceptance** | Custom headers appear in outgoing requests. Sensitive header values are redacted in error messages via `_redact_sensitive`. |
| **Effort** | Small (2–3 hr) |

---

### 3.2 · Normalised usage extraction

| | |
|---|---|
| **Rationale** | Not all providers return usage in the same shape; some omit it entirely. Current code handles OpenAI and Anthropic key names, but silently returns 0 when usage is absent. |
| **API additions** | Optional `usage_estimator: Callable[[Sequence[dict], LLMResponse], TokenUsage] | None` on `Provider` or as a `checked_complete` kwarg. New metadata flag `usage_estimated: bool` on `PatternResult`. |
| **File** | `provider.py`, `patterns/base.py` |
| **Acceptance** | When provider omits usage, the estimator callback is invoked. Metadata distinguishes estimated vs. provider-supplied usage. |
| **Effort** | Small–Medium (3–4 hr) |

---

### 3.3 · Richer tool-call error metadata

| | |
|---|---|
| **Rationale** | `_execute_tool_call` currently returns a flat error string. Callers have no structured way to detect which tools failed or why. |
| **API additions** | New metadata keys: `tool_errors: list[dict]` (each with `tool_name`, `error_type`, `round`). Optional per-tool observation formatter hook: `Tool(..., format_observation=None)`. |
| **File** | `patterns/react_loop.py`, `types.py` |
| **Acceptance** | After a failed tool call, `result.metadata["tool_errors"]` contains a structured entry. Custom formatter transforms raw tool output before it enters the conversation. |
| **Effort** | Small (2–3 hr) |

---

### 3.4 · Build verification in CI

| | |
|---|---|
| **Rationale** | `python -m build` only runs in the tag-based publish workflow. A broken `pyproject.toml` or missing `py.typed` marker would not be caught on PRs. |
| **Fix** | Add `python -m build --sdist --wheel` and `twine check dist/*` steps to the CI workflow. |
| **File** | `.github/workflows/ci.yml` |
| **Acceptance** | PRs that break the package build fail CI. |
| **Effort** | Trivial (30 min) |

---

## Tier 4 — Ecosystem & Developer Experience

> Polish, documentation, and testing maturity that make the library
> production-grade.

---

### 4.1 · Integration test harness

| | |
|---|---|
| **Rationale** | The `@pytest.mark.integration` marker is defined and documented but zero tests use it. The library claims broad compatibility across OpenAI-like endpoints but has no opt-in verification. |
| **Scope** | Add opt-in integration tests (gated by env vars) for: OpenAI, Ollama (local), and one fast provider (Groq or Together). Shared fixtures with env-var–driven config. |
| **File** | New `tests/integration/` directory |
| **Acceptance** | `pytest -m integration` runs real calls. `pytest -m "not integration"` (the default) skips them. CI runs unit tests only; a manual workflow dispatch runs integration. |
| **Effort** | Medium (4–6 hr) |

---

### 4.2 · Examples as CI smoke tests

| | |
|---|---|
| **Rationale** | Five examples exist but are never exercised. Example drift is likely over time. |
| **Scope** | Add a pytest fixture or conftest that imports each example module and verifies it is syntactically valid and importable. For examples that can run with `MockProvider`, execute them as actual tests. |
| **File** | New `tests/test_examples.py` |
| **Acceptance** | A broken example import fails CI. |
| **Effort** | Small (1–2 hr) |

---

### 4.3 · "Build your own pattern" guide

| | |
|---|---|
| **Rationale** | Architecture is extensible (`checked_complete`, `CostTracker`, immutable metadata) but users need a crisp recipe for writing custom patterns. |
| **Scope** | New `docs/custom-patterns.md`: use `checked_complete`, return `PatternResult` with `MappingProxyType` metadata, propagate `max_cost`, follow error/cost conventions. Include a minimal worked example. |
| **File** | `docs/custom-patterns.md`, link from `README.md` |
| **Acceptance** | A new contributor can follow the guide and implement a working custom pattern without reading the library source. |
| **Effort** | Small (2–3 hr) |

---

### 4.4 · Troubleshooting guide

| | |
|---|---|
| **Rationale** | No `docs/TROUBLESHOOTING.md` for common issues: tool timeouts, consensus not converging, budget exhaustion, sync wrapper errors in Jupyter. |
| **File** | New `docs/troubleshooting.md`, link from `README.md` |
| **Effort** | Small (2 hr) |

---

### 4.5 · Fix documentation drift

| | |
|---|---|
| **Items** | 1) `README.md` says "300 tests at 83% coverage" — update to actual count. 2) `SECURITY.md` references "structured output mode" which does not yet exist — reword or gate on 2.1. 3) `BUILD_SPEC.md` still references `pydantic` dependency — update. |
| **Effort** | Trivial (30 min) |

---

### 4.6 · Makefile / task runner

| | |
|---|---|
| **Rationale** | No `make test`, `make lint`, `make build` shortcuts. Contributors must memorize pytest/ruff/mypy flags. |
| **File** | New `Makefile` with targets: `dev-setup`, `lint`, `format`, `type-check`, `test`, `coverage`, `build`, `clean`. |
| **Effort** | Small (1 hr) |

---

## Explicit Non-Goals for v0.2

To prevent scope creep, the following are **out of scope**:

| Non-goal | Rationale |
|----------|-----------|
| Agent memory / persistent state | Framework creep — `Kit` is session-scoped by design |
| Workflow DAG / graph runtime | Framework creep — use LangGraph if you need this |
| Prompt template DSL | Library consumers bring their own prompts |
| Built-in vector DB / retrieval | Out of scope — RAG is an application concern |
| Provider-specific SDK dependencies | Violates zero-dep principle |
| Dashboard / spend UI | Platform creep |
| Multi-agent handoff / orchestration | Framework creep |
| tree_of_thought pattern | Deferred to v0.3; most complex pattern, needs research |
| Anthropic native provider | Deferred to v0.3; requires message format converter |

---

## Release Plan

### Milestone: v0.2.0

**Gate:** All Tier 1 items resolved. At least one Tier 2 item shipped.

| Phase | Items | Duration |
|-------|-------|----------|
| **Phase 1: Correctness** | 1.1–1.6 | 1 week |
| **Phase 2: Features** | 2.1 (structured), 2.2 (streaming), 2.3 (consensus rationale) | 2 weeks |
| **Phase 3: Maturity** | 3.1–3.4, 4.1–4.6 | 1 week |
| **Phase 4: Release** | Version bump, CHANGELOG, tag, publish | 1 day |

### Milestone: v0.3.0 (sketch)

- tree_of_thought pattern (beam search)
- Anthropic native provider + message converter
- TraceEntry + ProgressCallback (observability hooks)
- OpenTelemetry span integration
- mkdocs documentation site

---

## How to Use This Document

1. **Pick up work:** Choose an item, create a branch `feature/<item-id>` or
   `fix/<item-id>`, implement, test, PR.
2. **Acceptance criteria are real:** Every item lists what "done" means.
   Do not merge without meeting them.
3. **Stay in scope:** If an implementation grows beyond the stated scope,
   stop and open a discussion issue.
4. **Update this doc:** When an item ships, move it to `CHANGELOG.md` and
   remove it from this file.
