# ExecutionKit: Composable LLM Reasoning Patterns

## Context

The monorepo at `D:/source/prompts` was analyzed by 13+ specialized agents across 4 rounds, plus 3 antagonistic reviewers in round 5. The original concept ("Lithom") was killed. The pivot: **ExecutionKit** — composable execution patterns where Python orchestrates real LLM calls.

**Existing codebase provides 60% of the foundation** — 28 production-ready execution patterns cataloged in `agentic-workflows-v2/` (see Appendix A).

### Antagonistic Review Verdict (Round 5)

Three hostile reviewers scored the v1 plan. Key findings incorporated below:

| Reviewer | Verdict | Score | Critical Fixes Required |
|----------|---------|-------|------------------------|
| **Market** | KILL (78%) | 7.6/10 | Quickstart must beat raw SDK. Drop "itertools" tagline unless compose() ships v0.1. |
| **Technical** | BLOCK | 7.5/10 | TaskGroup kills partial ToT results. No default cost budget. Tool timeouts missing. NaN scores unhandled. Anthropic message conversion is 150+ LOC, not a "thin wrapper." |
| **API Design** | REJECT | 7.1/10 | No session/client pattern. Composition broken. Jupyter sync wrappers broken. `_engine/` private but needed by custom patterns. |

**All MUST-FIX items are resolved in this plan revision.**

---

## Package Structure

```
executionkit/
  pyproject.toml
  .gitignore
  .github/workflows/ci.yml
  src/executionkit/
    __init__.py                 # Public: tree_of_thought, react_loop, consensus, refine_loop, Kit
    py.typed                    # PEP 561 marker
    provider.py                 # LLMProvider Protocol + LLMResponse + error hierarchy
    types.py                    # PatternResult[T], TraceEntry, TokenUsage, Tool, Evaluator
    kit.py                      # NEW: Kit session class (binds provider + config) [FIX: api-2]
    compose.py                  # NEW: pipe() + merge_results() [FIX: api-4]
    patterns/
      __init__.py
      _base.py                  # NEW: _checked_complete() — score validation, finish_reason, budget [FIX: tech-5]
      tree_of_thought.py        # beam search with partial-result resilience [FIX: tech-2]
      react_loop.py             # tool loop with per-tool timeout [FIX: tech-3]
      consensus.py              # parallel voting with agreement_ratio [FIX: tech-5c]
      refine_loop.py            # iterative improvement with NaN guards [FIX: tech-5a]
    engine/                     # PUBLIC (was _engine/) [FIX: api-6]
      __init__.py               # Public: RetryConfig, gather_resilient, ConvergenceDetector
      context.py
      retry.py
      parallel.py               # gather_resilient (return_exceptions) + gather_strict (TaskGroup)
      convergence.py            # NaN-safe ConvergenceDetector [FIX: tech-5a]
      json_extraction.py
      message_converter.py      # NEW: OpenAI <-> Anthropic message history conversion [FIX: tech-4]
    providers/
      __init__.py
      _openai.py
      _ollama.py
      _anthropic.py             # Full message history conversion, not just schema [FIX: tech-4]
      _mock.py
  tests/
    conftest.py
    test_tree_of_thought.py
    test_react_loop.py
    test_consensus.py
    test_refine_loop.py
    test_engine.py
    test_providers.py
    test_message_converter.py   # NEW: OpenAI <-> Anthropic round-trip tests [FIX: tech-4]
    test_kit.py                 # NEW: session tests [FIX: api-2]
    test_compose.py             # NEW: pipe/compose tests [FIX: api-4]
    test_cost.py
  examples/
    basic_tot.py
    basic_react.py
    basic_consensus.py
    basic_refine.py
    basic_compose.py            # NEW: pipe(refine_loop, consensus) example
    quickstart_github.py
    quickstart_ollama.py
    quickstart_notebook.ipynb   # NEW: Jupyter-safe example [FIX: api-5]
```

**Dependencies:**
```toml
[project]
name = "executionkit"
version = "0.1.0"
description = "Composable LLM reasoning patterns"
requires-python = ">=3.11"
dependencies = ["pydantic>=2.0,<3"]

[project.optional-dependencies]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.40"]
all = ["executionkit[openai,anthropic]"]
dev = [
    "pytest>=7.0", "pytest-asyncio>=0.21", "pytest-cov>=4.0",
    "hypothesis>=6.0", "ruff>=0.4", "mypy>=1.10",
]
```

Note: Tagline changed from "itertools for LLM reasoning" to just "Composable LLM reasoning patterns" — the itertools comparison was a liability per market review. Earned back only if compose() proves elegant.

---

## Core Type Definitions

### provider.py — Protocol + Response + Errors

```python
@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: type | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...

@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def input_tokens(self) -> int: ...
    @property
    def output_tokens(self) -> int: ...
    @property
    def total_tokens(self) -> int: ...
    @property
    def has_tool_calls(self) -> bool: ...
    @property
    def was_truncated(self) -> bool:
        return self.finish_reason == "length"  # [FIX: tech-5d]

# Error hierarchy (unchanged)
class LLMError(Exception): ...
class RateLimitError(LLMError): ...
class AuthenticationError(LLMError): ...
class ModelNotFoundError(LLMError): ...
class ContextLengthError(LLMError): ...
class ProviderError(LLMError): ...

# NEW [FIX: tech-5d]
class TruncatedResponseError(LLMError):
    """Response was cut off (finish_reason='length'). Retry with higher max_tokens."""
```

### types.py — Results, Tools, Callbacks

```python
@dataclass(frozen=True, slots=True)
class TokenUsage:  # RENAMED from CostMetrics [FIX: api-naming]
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    def __add__(self, other: TokenUsage) -> TokenUsage: ...

@dataclass(slots=True)
class PatternResult(Generic[T]):
    value: T
    score: float | None = None
    cost: TokenUsage = field(default_factory=TokenUsage)
    iterations: int = 0
    trace: list[TraceEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return str(self.value)  # [FIX: api-3] — print(result) works without .value

    def __iter__(self):
        yield self.value       # [FIX: api-3] — value, = result unpacking
        yield self.cost

@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Awaitable[str]]
    timeout: float = 30.0  # [FIX: tech-5b] — per-tool timeout in seconds

    def to_openai_schema(self) -> dict[str, Any]: ...
    def to_anthropic_schema(self) -> dict[str, Any]: ...

# Evaluator: (text, provider) -> score in [0.0, 1.0]
Evaluator = Callable[[str, LLMProvider], Awaitable[float]]
ProgressCallback = Callable[[TraceEntry], None]
```

### kit.py — Session class [FIX: api-2]

```python
@dataclass
class Kit:
    """Binds a provider + shared config. Eliminates boilerplate for multi-call usage."""
    provider: LLMProvider
    retry: RetryConfig | None = None
    on_progress: ProgressCallback | None = None
    max_cost: TokenUsage | None = None

    async def tree_of_thought(self, prompt: str, **kwargs) -> PatternResult[str]:
        return await tree_of_thought(self.provider, prompt,
            retry=self.retry, on_progress=self.on_progress, max_cost=self.max_cost, **kwargs)

    async def react_loop(self, prompt: str, tools: Sequence[Tool], **kwargs) -> PatternResult[str]:
        return await react_loop(self.provider, prompt, tools,
            retry=self.retry, on_progress=self.on_progress, max_cost=self.max_cost, **kwargs)

    async def consensus(self, prompt: str, **kwargs) -> PatternResult:
        return await consensus(self.provider, prompt,
            retry=self.retry, on_progress=self.on_progress, **kwargs)

    async def refine_loop(self, prompt: str, **kwargs) -> PatternResult[str]:
        return await refine_loop(self.provider, prompt,
            retry=self.retry, on_progress=self.on_progress, max_cost=self.max_cost, **kwargs)

# Usage:
# kit = Kit(provider, retry=RetryConfig(max_retries=5))
# r1 = await kit.consensus("prompt 1")
# r2 = await kit.refine_loop("prompt 2")  # No repeated provider/retry args
```

### compose.py — Pattern composition [FIX: api-4]

```python
async def pipe(
    provider: LLMProvider,
    prompt: str,
    *steps: Callable,  # Pattern functions or lambdas
    **shared_kwargs: Any,
) -> PatternResult:
    """Chain patterns sequentially. Output of step N feeds as prompt to step N+1.
    Costs and traces are merged across all steps."""
    merged_cost = TokenUsage()
    merged_trace: list[TraceEntry] = []
    current_input = prompt

    for step_fn in steps:
        result = await step_fn(provider, current_input, **shared_kwargs)
        current_input = str(result.value)
        merged_cost = merged_cost + result.cost
        merged_trace.extend(result.trace)

    return PatternResult(
        value=result.value,
        score=result.score,
        cost=merged_cost,
        iterations=len(steps),
        trace=merged_trace,
    )

# Usage:
# result = await pipe(provider, "Write a haiku", refine_loop, consensus)
# result.cost  # Total across both patterns
```

---

## Engine Internals (PUBLIC — `executionkit.engine`)

**[FIX: api-6]** — Renamed from `_engine/` to `engine/`. All utilities are public so users can build custom patterns on the same infrastructure.

### engine/parallel.py — TWO modes [FIX: tech-2]

```python
async def gather_resilient(
    coros: Sequence[Coroutine],
    max_concurrency: int = 10,
) -> list[Any | Exception]:
    """Run coroutines with bounded concurrency. RETURNS exceptions instead of raising.
    Use for ToT beam search where partial results are acceptable."""
    semaphore = asyncio.Semaphore(max_concurrency)
    async def run(coro):
        async with semaphore:
            return await coro
    return await asyncio.gather(*[run(c) for c in coros], return_exceptions=True)

async def gather_strict(
    coros: Sequence[Coroutine],
    max_concurrency: int = 10,
) -> list[Any]:
    """Run coroutines with bounded concurrency. RAISES on first failure (via TaskGroup).
    Use for consensus where all samples must succeed."""
    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[Any] = [None] * len(coros)
    async def run(i, coro):
        async with semaphore:
            results[i] = await coro
    async with asyncio.TaskGroup() as tg:
        for i, coro in enumerate(coros):
            tg.create_task(run(i, coro))
    return results
```

**ToT uses `gather_resilient`** — a failed evaluation scores as 0.0, branch continues.
**Consensus uses `gather_strict`** — all samples must complete or pattern fails.

### engine/convergence.py — NaN-safe [FIX: tech-5a]

```python
import math

@dataclass
class ConvergenceDetector:
    delta_threshold: float = 0.01
    patience: int = 2
    score_threshold: float | None = None
    _scores: list[float] = field(default_factory=list, init=False)
    _stale_count: int = field(default=0, init=False)

    def should_stop(self, score: float) -> bool:
        if math.isnan(score) or not (0.0 <= score <= 1.0):
            raise ValueError(f"Evaluator returned invalid score: {score}. Must be in [0.0, 1.0].")
        self._scores.append(score)
        if self.score_threshold is not None and score >= self.score_threshold:
            return True
        if len(self._scores) < 2:
            return False
        delta = score - self._scores[-2]
        if delta < self.delta_threshold:
            self._stale_count += 1
        else:
            self._stale_count = 0
        return self._stale_count >= self.patience
```

### engine/message_converter.py — NEW [FIX: tech-4]

```python
def openai_to_anthropic(messages: list[dict]) -> list[dict]:
    """Convert OpenAI-format message history to Anthropic format.

    Handles:
    - tool_calls array -> content blocks with type="tool_use"
    - role="tool" messages -> role="user" with type="tool_result" blocks
    - Merging consecutive user messages (Anthropic requires alternating roles)
    - System message extraction (Anthropic uses top-level system param)
    """

def anthropic_to_openai(messages: list[dict]) -> list[dict]:
    """Convert Anthropic-format message history to OpenAI format.

    Handles:
    - content blocks with type="tool_use" -> tool_calls array
    - role="user" with type="tool_result" -> role="tool" messages
    - Re-separating merged user messages
    """
```

Estimated ~150 LOC. The AnthropicProvider calls `openai_to_anthropic()` on the full message history before each `provider.complete()` call, and normalizes the response back to OpenAI format. This is NOT a thin wrapper — it is the most complex provider code.

---

## Pattern Algorithms (Post-Review)

### patterns/_base.py — Shared safety checks [FIX: tech-5]

```python
async def _checked_complete(
    provider: LLMProvider,
    messages: Sequence[dict],
    tracker: CostTracker,
    budget: TokenUsage | None,
    retry: RetryConfig | None,
    **kwargs,
) -> LLMResponse:
    """Wraps provider.complete() with budget check, retry, and truncation detection."""
    # Budget guard: check BEFORE each call, not per-depth
    if budget and tracker.total_tokens >= budget.input_tokens + budget.output_tokens:
        raise BudgetExhaustedError(f"Budget of {budget} exceeded")

    response = await with_retry(provider.complete, retry or _DEFAULT_RETRY, messages, **kwargs)

    # Truncation warning in metadata
    if response.was_truncated:
        # Don't raise, but flag it — patterns decide how to handle
        pass

    tracker.record(response)
    return response

def _validate_score(score: float) -> float:
    """Validate evaluator output. Raises ValueError on NaN or out-of-range."""
    if math.isnan(score) or not (0.0 <= score <= 1.0):
        raise ValueError(f"Evaluator returned invalid score: {score}. Must be in [0.0, 1.0].")
    return score
```

### tree_of_thought() — with partial-result resilience [FIX: tech-2, tech-3]

```python
async def tree_of_thought(
    provider: LLMProvider,
    prompt: str,
    *,
    num_branches: int = 3,
    beam_width: int = 2,
    max_depth: int = 3,
    evaluator: Evaluator | None = None,
    temperature: float = 0.9,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = TokenUsage(input_tokens=500_000, output_tokens=200_000, llm_calls=100),
    # ^^^ [FIX: tech-3] DEFAULT BUDGET — 100 calls max
    on_progress: ProgressCallback | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

**Key fix:** Evaluations use `gather_resilient()`. Failed evaluations score as 0.0:
```
# EVALUATE with partial-result resilience
eval_results = await gather_resilient(
    [evaluator(c, provider) for c in candidates]
)
scored = []
for candidate, result in zip(candidates, eval_results):
    if isinstance(result, Exception):
        scored.append((candidate, 0.0))  # Failed eval = worst score
    else:
        scored.append((candidate, _validate_score(result)))
```

Budget check happens per-call via `_checked_complete()`, not per-depth.

### react_loop() — with tool timeouts [FIX: tech-5b]

```python
async def react_loop(
    provider: LLMProvider,
    prompt: str,
    tools: Sequence[Tool],
    *,
    max_rounds: int = 8,
    max_observation_chars: int = 12000,
    tool_timeout: float | None = None,  # Override per-tool default (Tool.timeout)
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    on_progress: ProgressCallback | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

**Key fix:** Tool execution wrapped in `asyncio.wait_for`:
```
for tc in response.tool_calls:
    call_id, name, args = normalize_tool_call(tc)
    tool = tool_map.get(name)
    timeout = tool_timeout or (tool.timeout if tool else 30.0)
    try:
        result = await asyncio.wait_for(tool.execute(**args), timeout=timeout)
    except asyncio.TimeoutError:
        result = json.dumps({"error": f"Tool '{name}' timed out after {timeout}s"})
    except Exception as exc:
        result = json.dumps({"error": str(exc)})
```

### consensus() — with agreement_ratio [FIX: tech-5c]

```python
async def consensus(
    provider: LLMProvider,
    prompt: str,
    *,
    num_samples: int = 5,
    strategy: VotingStrategy | str = "majority",
    response_format: type[T] | None = None,
    temperature: float = 0.9,
    max_tokens: int = 4096,
    max_concurrency: int = 5,
    on_progress: ProgressCallback | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[T]:
```

**Key fix:** `metadata` includes `agreement_ratio`:
```
winner_count = canonical.count(canonical[winner_index])
agreement_ratio = winner_count / len(canonical)

return PatternResult(
    value=parsed[winner_index],
    metadata={
        "agreement_ratio": agreement_ratio,  # 0.2 = random, 1.0 = unanimous
        "unique_responses": len(set(canonical)),
        "strategy": strategy,
    },
    ...
)
```

### refine_loop() — with NaN guard [FIX: tech-5a]

All evaluator calls go through `_validate_score()`. If the first eval returns NaN, it raises immediately instead of silently producing garbage.

---

## Sync Wrappers — Jupyter-Safe [FIX: api-5]

```python
# __init__.py
import asyncio

def _run_sync(coro):
    """Run async coroutine synchronously. Jupyter-safe."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Inside Jupyter or async context — use nest_asyncio
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(coro)
    else:
        return asyncio.run(coro)

# Each pattern gets a sync variant:
def consensus_sync(provider, prompt, **kwargs):
    return _run_sync(consensus(provider, prompt, **kwargs))
```

`nest_asyncio` added as optional dependency. If not installed, sync wrappers raise a clear error when called from Jupyter: "Install nest_asyncio for Jupyter support: pip install nest_asyncio".

---

## Anthropic Provider — Full Message Conversion [FIX: tech-4]

```python
# providers/_anthropic.py (~120 LOC, not 60)
@dataclass
class AnthropicProvider:
    model: str
    api_key: str = field(default="", repr=False)
    _client: Any = field(default=None, repr=False, init=False)

    async def complete(self, messages, *, tools=None, **kwargs) -> LLMResponse:
        from .._engine.message_converter import openai_to_anthropic

        # Extract system message (Anthropic uses top-level param)
        system_text, converted_messages = openai_to_anthropic(list(messages))

        # Convert tool schemas from OpenAI to Anthropic format
        anthropic_tools = [_convert_tool_schema(t) for t in (tools or [])]

        client = self._get_client()
        response = await client.messages.create(
            model=self.model,
            system=system_text,
            messages=converted_messages,
            tools=anthropic_tools or NOT_GIVEN,
            **kwargs,
        )

        # Normalize response back to OpenAI format
        content, tool_calls = _extract_response(response)
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,  # Already in OpenAI-normalized format
            finish_reason=_map_stop_reason(response.stop_reason),
            usage={"input_tokens": response.usage.input_tokens,
                   "output_tokens": response.usage.output_tokens},
            raw=response,
        )
```

---

## What to Extract vs Write New

### EXTRACT from `agentic-workflows-v2/agentic_v2/`

| Target | Source | Adaptation |
|--------|--------|------------|
| `engine/context.py` | `engine/context.py` | Strip to ~120 LOC |
| `engine/retry.py` | `engine/step.py:18-68` | Change retry_on defaults |
| `engine/parallel.py` | `engine/dag_executor.py:194+` | Split into gather_resilient + gather_strict |
| `engine/json_extraction.py` | `agents/json_extraction.py` | Extract verbatim |
| `patterns/react_loop.py` | `engine/tool_execution.py:220-246` | normalize_tool_call verbatim |
| `providers/_openai.py` | `tools/llm/provider_adapters.py` | Merge with base_url |
| `providers/_ollama.py` | `tools/llm/provider_adapters.py` | Add asyncio.to_thread |
| `providers/_anthropic.py` | `models/backends_cloud.py:289-300` | Full message converter |

### WRITE NEW

| File | LOC | Why |
|------|-----|-----|
| `provider.py` | 90 | Protocol + LLMResponse + TruncatedResponseError |
| `types.py` | 130 | PatternResult (with __str__/__iter__), TokenUsage, Tool (with timeout) |
| `kit.py` | 60 | Session class binding provider + config |
| `compose.py` | 50 | pipe() + merge logic |
| `patterns/_base.py` | 80 | _checked_complete, _validate_score, BudgetExhaustedError |
| `engine/convergence.py` | 70 | NaN-safe ConvergenceDetector |
| `engine/message_converter.py` | 150 | OpenAI <-> Anthropic full conversion |
| `providers/_mock.py` | 80 | Configurable mock |
| `patterns/consensus.py` | 170 | With agreement_ratio |
| `patterns/refine_loop.py` | 170 | With NaN guards |
| `patterns/react_loop.py` | 220 | With tool timeouts |
| `patterns/tree_of_thought.py` | 270 | With gather_resilient, default budget |

**Total: ~1,900 LOC** (up from 1,700 — message converter and safety checks add ~200).

---

## Phased Build Sequence

### Phase 1a: Type Foundation (Day 1)
1. `pyproject.toml`, `.gitignore`, `py.typed`
2. `provider.py` — Protocol, LLMResponse (with was_truncated), errors
3. `types.py` — PatternResult (with __str__/__iter__), TokenUsage, Tool (with timeout), TraceEntry
4. `providers/_mock.py` — MockProvider
5. `tests/conftest.py` — fixtures

### Phase 1b: Engine (Day 2)
6. Tests first: `tests/test_engine.py`
7. `engine/retry.py` — RetryConfig + with_retry
8. `engine/parallel.py` — gather_resilient + gather_strict
9. `engine/convergence.py` — NaN-safe ConvergenceDetector
10. `engine/context.py` — simplified ExecutionContext
11. `engine/json_extraction.py` — balanced-brace fallback
12. `engine/message_converter.py` — OpenAI <-> Anthropic + tests

### Phase 1c: Providers + Cost + Kit (Day 3)
13. Tests first: `tests/test_providers.py`, `tests/test_message_converter.py`
14. `providers/_openai.py`, `_ollama.py`, `_anthropic.py` (with full conversion)
15. `providers/__init__.py` — conditional imports
16. `cost.py` — CostTracker
17. `kit.py` — Session class
18. `patterns/_base.py` — _checked_complete, _validate_score

### Phase 2a: Consensus (Day 4)
19. Tests first (including hypothesis property tests)
20. `patterns/consensus.py` with agreement_ratio

### Phase 2b: Refine Loop (Day 5)
21. Tests first
22. `patterns/refine_loop.py` with NaN guards

### Phase 2c: ReAct (Days 6-7)
23. Tests first (multi-turn with tool timeouts)
24. `patterns/react_loop.py` with asyncio.wait_for per tool

### Phase 2d: Tree of Thought (Days 7-8)
25. Tests first
26. `patterns/tree_of_thought.py` with gather_resilient + default budget

### Phase 3: Polish + Release (Days 9-10)
27. `compose.py` — pipe()
28. `__init__.py` — public exports + Jupyter-safe sync wrappers
29. Examples (7 files including notebook)
30. README.md, CI pipeline
31. Final: ruff + mypy --strict + pytest --cov-fail-under=80

### Phase 4: v0.2 (DEFER)
- OpenTelemetry tracing (optional)
- Streaming intermediate results
- Additional composition operators (fan-out, conditional)

---

## Test Strategy

### Test Categories (per pattern)

1. **Unit tests** — MockProvider with canned responses. Verify message formation, loop termination, cost tracking, trace entries.
2. **Edge cases** — Budget exhaustion mid-call, all branches scored 0, NaN evaluator, tool timeout, empty responses, finish_reason="length", zero-agreement consensus.
3. **Property-based** (hypothesis) — Consensus majority always returns most frequent. Convergence detector always terminates. gather_resilient never raises.
4. **Message converter round-trip** — OpenAI -> Anthropic -> OpenAI produces equivalent messages for all tool-call scenarios.
5. **Integration** — `@pytest.mark.integration` (skipped in CI).

### Coverage Targets
- 80% overall, 90% for `patterns/`, 100% for `provider.py` and `types.py`

### CI Pipeline
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python-version }}" }
      - run: pip install -e ".[dev,all]"
      - run: ruff check src/executionkit && ruff format --check src/executionkit
      - run: mypy --strict src/executionkit
      - run: pytest tests/ -m "not integration" --cov=executionkit --cov-fail-under=80 -x
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Cost explosion** | DEFAULT max_cost on ToT (100 calls). Per-call budget check via _checked_complete(). BudgetExhaustedError raised, not silent. |
| **Partial failures in ToT** | gather_resilient returns exceptions as values. Failed evals score 0.0. Pattern continues with surviving branches. |
| **Tool hangs** | asyncio.wait_for with Tool.timeout (default 30s). Timeout produces error JSON, not hang. |
| **NaN evaluator scores** | _validate_score raises ValueError immediately. ConvergenceDetector validates on entry. |
| **Anthropic message format** | Dedicated message_converter.py (~150 LOC). Round-trip tested. Not hidden in provider. |
| **Truncated responses** | LLMResponse.was_truncated property. Patterns can retry with doubled max_tokens or flag in metadata. |
| **Paradigm lock-in** | Stateless functions. Drop-in replaceable. |
| **Jupyter broken** | nest_asyncio detection + clear error message. |
| **No composition** | pipe() ships v0.1. Costs and traces merge automatically. |
| **Private engine** | engine/ is public. Custom patterns reuse RetryConfig, gather_resilient, ConvergenceDetector. |

---

## Stability Policy

- `LLMProvider` Protocol is **frozen for 0.x**. New capabilities via optional methods checked with `hasattr()`.
- `PatternResult` fields frozen for 0.x. New data goes in `.metadata`.
- `engine/` public API: RetryConfig, gather_resilient, gather_strict, ConvergenceDetector, with_retry — stable for 0.x.
- SemVer: 0.x means breaking changes possible between minors. 1.0 locks the public API.

---

## Appendix A: 28 Extractable Patterns in D:/source/prompts

| # | Pattern | Source File | Category | LOC |
|---|---------|------------|----------|-----|
| 1 | DAG Definition + Cycle Detection | engine/dag.py | Execution | 261 |
| 2 | Dynamic Parallel DAG Executor (FIRST_COMPLETED) | engine/dag_executor.py | Execution | 294 |
| 3 | Pipeline + Parallel Groups + Conditional Branching | engine/pipeline.py | Execution | 458 |
| 4 | Unified Workflow Executor + Global Timeout | engine/executor.py | Execution | 463 |
| 5 | Step Lifecycle + Retry (4 strategies + jitter) | engine/step.py | Execution | 481 |
| 6 | Multi-turn Tool Execution Loop | engine/tool_execution.py | Execution | 445 |
| 7 | Isolated Task Runtime (Subprocess / Docker) | engine/runtime.py | Execution | 377 |
| 8 | ReAct Agent Loop (state machine lifecycle) | agents/base.py | Reasoning | 542 |
| 9 | Multi-Pass Self-Refinement (Reviewer) | agents/reviewer.py | Reasoning | 371 |
| 10 | Orchestrator / LLM Task Decomposition | agents/orchestrator.py | Reasoning | 542 |
| 11 | Safe AST Expression Evaluator | engine/expressions.py | Reasoning | 492 |
| 12 | Sliding-Window Memory + Auto-Summarization | agents/memory.py | Reasoning | 267 |
| 13 | Reciprocal Rank Fusion | rag/retrieval.py | Aggregation | 35 |
| 14 | BM25 Keyword Index (pure Python) | rag/retrieval.py | Aggregation | 157 |
| 15 | LLM Reranker (semaphore-bounded) | rag/reranking.py | Aggregation | 205 |
| 16 | Capability-Based Agent Scoring / Best-of-N | agents/orchestrator.py | Aggregation | 30 |
| 17 | Loop-Until Convergence | engine/step.py | Flow Control | 16 |
| 18 | Conditional Branching (when/unless guards) | engine/step.py + pipeline.py | Flow Control | 45 |
| 19 | Cascade Skip (BFS Failure Propagation) | engine/dag_executor.py | Flow Control | 15 |
| 20 | Circuit Breaker (3-state) | models/model_stats.py | Flow Control | 381 |
| 21 | Adaptive Rate Limiting (Token Buckets) | models/rate_limit_tracker.py | Flow Control | 396 |
| 22 | Fallback Chain + Cross-Tier Degradation | models/smart_router.py | Flow Control | 537 |
| 23 | JSON Extraction with Candidate Cascade | engine/llm_output_parsing.py | Output | 90 |
| 24 | Structured Output Normalization | engine/llm_output_parsing.py | Output | 100 |
| 25 | Sentinel Artifact Parsing (FILE/ENDFILE) | engine/llm_output_parsing.py | Output | 100 |
| 26 | Balanced-Brace JSON Extraction | agents/json_extraction.py | Output | 156 |
| 27 | Checkpoint Store + SQLite Resume | adapters/native/engine.py | Execution | 289 |
| 28 | Step State Machine (8-state lifecycle) | engine/step_state.py | Flow Control | 91 |

**Total extractable LOC across all 28 patterns: ~7,866**

---

## Verification

1. `ruff check src/executionkit` — passes
2. `ruff format --check src/executionkit` — passes
3. `mypy --strict src/executionkit` — passes
4. `pytest tests/ -m "not integration" --cov=executionkit --cov-fail-under=80` — passes
5. `examples/quickstart_github.py` — works end-to-end with GITHUB_TOKEN
6. `examples/quickstart_ollama.py` — works with local Ollama, zero cloud deps
7. `examples/quickstart_notebook.ipynb` — works in Jupyter without RuntimeError
8. `examples/basic_compose.py` — pipe(refine_loop, consensus) merges costs correctly
9. `examples/basic_tot.py` — produces valid tree, respects default budget
10. `examples/basic_react.py` — tool timeout triggers gracefully
11. `examples/basic_consensus.py` — agreement_ratio in metadata
12. `examples/basic_refine.py` — converges within max_iterations
