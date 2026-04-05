# ExecutionKit: Reliable LLM Calls Through Voting, Refinement, and Search

## Context

The monorepo at `D:/source/prompts` was analyzed by 13+ specialized agents across 4 rounds, 3 antagonistic reviewers in round 5, then 3 constructive expert reviewers in round 6. The original concept ("Lithom") was killed. The pivot: **ExecutionKit** — composable execution patterns where Python orchestrates real LLM calls.

**Existing codebase provides 60% of the foundation** — 28 production-ready execution patterns cataloged in `agentic-workflows-v2/` (see Appendix A).

### Review History

| Round | Reviewers | Verdict | Key Outcome |
|-------|-----------|---------|-------------|
| 5 — Antagonistic | Market (KILL 78%), Technical (BLOCK), API (REJECT) | 12 MUST-FIX items | Added gather_resilient, default budgets, tool timeouts, Kit session, pipe(), NaN guards, Jupyter-safe sync, public engine/ |
| 6 — Constructive | Sr. Architect (NEEDS WORK), Sr. Engineer (NEEDS REFINEMENT), OSS Expert (NEEDS POLISH) | 8 architectural fixes + launch readiness gaps | Added extension Protocols, ToolCall dataclass, error hierarchy restructure, CancelledError guards, observability fields, PyPI metadata, hero examples, CONTRIBUTING.md |

---

## Package Structure

```
executionkit/
  pyproject.toml
  .gitignore
  .github/workflows/ci.yml
  CHANGELOG.md
  CONTRIBUTING.md
  LICENSE                       # MIT
  src/executionkit/
    __init__.py                 # Public exports + Jupyter-safe sync wrappers
    __main__.py                 # CLI: executionkit check/demo/version [R6-oss-2]
    py.typed                    # PEP 561
    provider.py                 # LLMProvider Protocol + extension Protocols + LLMResponse + ToolCall + errors
    types.py                    # PatternResult[T], TraceEntry, TokenUsage, Tool, Evaluator, PatternStep
    kit.py                      # Kit session class (binds provider + config)
    compose.py                  # pipe() with budget-aware accumulation [R6-arch-4]
    patterns/
      __init__.py
      base.py                   # PUBLIC: checked_complete, validate_score [R6-arch-2]
      tree_of_thought.py
      react_loop.py
      consensus.py
      refine_loop.py
    engine/                     # PUBLIC
      __init__.py
      context.py
      retry.py
      parallel.py               # gather_resilient + gather_strict
      convergence.py
      json_extraction.py
    providers/
      __init__.py
      _openai.py
      _ollama.py
      _anthropic.py
      _conversion.py            # OpenAI <-> Anthropic message conversion [R6-arch-3]
      _mock.py
  tests/
    conftest.py
    test_tree_of_thought.py
    test_react_loop.py
    test_consensus.py
    test_refine_loop.py
    test_engine.py
    test_providers.py
    test_conversion.py          # Round-trip + edge case tests
    test_kit.py
    test_compose.py
    test_cost.py
    test_concurrency.py         # Semaphore release, CancelledError, ExceptionGroup [R6-eng-1]
  examples/
    quickstart_openai.py        # Zero-config beyond API key [R6-oss-4]
    quickstart_ollama.py
    quickstart_notebook.ipynb
    classification.py           # Consensus for reliable classification [R6-oss-4]
    structured_extraction.py    # refine_loop + Pydantic [R6-oss-4]
    compose_pipeline.py         # pipe(refine_loop, consensus) [R6-oss-1]
    custom_provider.py          # 20-line LLMProvider implementation [R6-oss-4]
    custom_evaluator.py         # Custom scoring function [R6-oss-4]
    error_handling.py           # BudgetExhaustedError, timeouts, retries [R6-oss-4]
    progress_tracking.py        # on_progress with rich/tqdm [R6-oss-4]
  docs/                         # mkdocs-material, auto-generated from docstrings [R6-oss-3]
    mkdocs.yml
    index.md
    patterns/
    providers/
    engine/
```

---

## pyproject.toml

```toml
[project]
name = "executionkit"
version = "0.1.0"
description = "Reliable LLM calls through voting, refinement, and search"
requires-python = ">=3.11"
license = "MIT"
readme = "README.md"
authors = [{name = "TBD"}]
keywords = [
    "llm", "reasoning", "consensus", "tree-of-thought", "react",
    "agent", "openai", "anthropic", "refinement", "voting",
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Typing :: Typed",
    "Framework :: AsyncIO",
]
dependencies = ["pydantic>=2.0,<3"]

[project.optional-dependencies]
openai = ["openai>=1.0"]
anthropic = ["anthropic>=0.40"]
all = ["executionkit[openai,anthropic]"]
dev = [
    "pytest>=7.0", "pytest-asyncio>=0.21", "pytest-cov>=4.0",
    "hypothesis>=6.0", "ruff>=0.4", "mypy>=1.10",
]
docs = ["mkdocs-material", "mkdocstrings[python]"]

[project.urls]
Homepage = "https://github.com/OWNER/executionkit"
Documentation = "https://OWNER.github.io/executionkit"
Repository = "https://github.com/OWNER/executionkit"
Issues = "https://github.com/OWNER/executionkit/issues"
Changelog = "https://github.com/OWNER/executionkit/blob/main/CHANGELOG.md"

[project.scripts]
executionkit = "executionkit.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/executionkit"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["integration: requires real LLM API (deselect with -m 'not integration')"]
filterwarnings = ["ignore::DeprecationWarning:asyncio"]

[tool.ruff]
target-version = "py311"
line-length = 88
select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "C4", "SIM", "TCH", "RUF", "D"]
[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.mypy]
strict = true
python_version = "3.11"
```

---

## Core Type Definitions

### provider.py — Protocol + Extension Protocols + Response + Errors

```python
from __future__ import annotations

# === Core Protocol (frozen for 0.x) ===
@runtime_checkable
class LLMProvider(Protocol):
    """Minimal LLM interface. All patterns accept this."""
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse: ...

# === Extension Protocols (defined now, used later) [R6-arch-1] ===
@runtime_checkable
class ToolCallingProvider(LLMProvider, Protocol):
    """Provider that supports tool/function calling."""
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...

@runtime_checkable
class StreamingProvider(LLMProvider, Protocol):
    """Provider that supports streaming (v0.2)."""
    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[LLMChunk]: ...

# === Response ===
@dataclass(frozen=True, slots=True)
class ToolCall:  # [R6-arch-6] — replaces list[dict]
    """Typed tool call, normalized across providers."""
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
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
        return self.finish_reason == "length"

# === Error Hierarchy [R6-arch-5] ===
class ExecutionKitError(Exception):
    """Root exception for all ExecutionKit errors."""

class LLMError(ExecutionKitError):
    """Provider-level errors (network, auth, rate limits)."""

class RateLimitError(LLMError): ...
class AuthenticationError(LLMError): ...
class ModelNotFoundError(LLMError): ...
class ContextLengthError(LLMError): ...
class ProviderError(LLMError): ...

class PatternError(ExecutionKitError):
    """Pattern-level errors (budget, consensus failure, max iterations)."""

class BudgetExhaustedError(PatternError): ...
class ConsensusFailedError(PatternError): ...
class MaxIterationsError(PatternError): ...
```

**Design decisions from R6-arch review:**
- `LLMProvider.complete()` no longer has `tools` or `response_format` in base Protocol. Tools are on `ToolCallingProvider`. This means small local models that can't do tool calling still satisfy `LLMProvider`.
- `ToolCall` dataclass replaces `list[dict[str, Any]]`. Prevents untyped dict sprawl. Providers normalize to this format.
- `StreamingProvider` defined now but unused until v0.2. Adding `stream()` later is additive, not a breaking change.
- Error hierarchy split into `LLMError` (provider-level, often retried automatically) and `PatternError` (pattern-level, policy decisions by the caller).

### types.py — Results, Tools, Callbacks

```python
@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    def __add__(self, other: TokenUsage) -> TokenUsage: ...

@dataclass(frozen=True, slots=True)
class TraceEntry:
    """Single step in a pattern's execution trace."""
    step: str               # "branch", "evaluate", "prune", "think", "act", "observe", "sample", "vote", "generate", "refine"
    iteration: int
    input: str              # First 200 chars
    output: str             # First 500 chars
    score: float | None
    duration_ms: float
    tokens_used: int
    request_id: str         # [R6-eng-6] UUID correlating all calls in one pattern invocation
    started_at: float       # [R6-eng-6] monotonic timestamp
    usage: dict[str, Any]   # [R6-eng-7] per-call token breakdown

@dataclass(frozen=True, slots=True)
class PatternResult(Generic[T]):
    value: T
    score: float | None = None
    cost: TokenUsage = field(default_factory=TokenUsage)
    iterations: int = 0
    trace: list[TraceEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""    # [R6-eng-6] same UUID as trace entries

    def __str__(self) -> str:
        return str(self.value)

    def __iter__(self):
        yield self.value
        yield self.cost

@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    execute: Callable[..., Awaitable[str]]
    timeout: float = 30.0

    def to_openai_schema(self) -> dict[str, Any]: ...
    def to_anthropic_schema(self) -> dict[str, Any]: ...

Evaluator = Callable[[str, LLMProvider], Awaitable[float]]
ProgressCallback = Callable[[TraceEntry], None]

# [R6-arch-8] Type-safe callable for pipe()
class PatternStep(Protocol):
    async def __call__(self, provider: LLMProvider, prompt: str, **kwargs: Any) -> PatternResult: ...
```

---

## Engine (PUBLIC — `executionkit.engine`)

### engine/parallel.py — CancelledError-safe [R6-eng-1]

```python
async def gather_resilient(
    coros: Sequence[Coroutine],
    max_concurrency: int = 10,
) -> list[Any | BaseException]:
    """Partial-result parallel execution. Returns exceptions as values.
    CancelledError propagates (not caught) — caller handles cancellation."""
    semaphore = asyncio.Semaphore(max_concurrency)
    async def run(coro):
        async with semaphore:
            return await coro
    try:
        return await asyncio.gather(*[run(c) for c in coros], return_exceptions=True)
    except asyncio.CancelledError:
        raise  # Never swallow cancellation

async def gather_strict(
    coros: Sequence[Coroutine],
    max_concurrency: int = 10,
) -> list[Any]:
    """All-or-nothing parallel execution. Wraps ExceptionGroup for clean handling."""
    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[Any] = [None] * len(coros)
    async def run(i, coro):
        async with semaphore:
            results[i] = await coro
    try:
        async with asyncio.TaskGroup() as tg:
            for i, coro in enumerate(coros):
                tg.create_task(run(i, coro))
    except ExceptionGroup as eg:
        # Unwrap single exceptions for clean caller handling
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from eg
        raise
    return results
```

### engine/retry.py — CancelledError guard [R6-eng-2]

```python
async def with_retry(fn, config, *args, **kwargs) -> T:
    """Execute fn with retry/backoff. NEVER retries CancelledError."""
    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except asyncio.CancelledError:
            raise  # [R6-eng-2] Immediate propagation, no retry
        except Exception as exc:
            last_error = exc
            if not config.should_retry(exc) or attempt == config.max_retries:
                raise
            delay = config.get_delay(attempt)
            await asyncio.sleep(delay)
    raise last_error  # unreachable
```

### engine/convergence.py — NaN-safe, patience=3 default [R6-eng-10]

```python
@dataclass
class ConvergenceDetector:
    delta_threshold: float = 0.01
    patience: int = 3           # [R6-eng-10] increased from 2
    score_threshold: float | None = None

    def should_stop(self, score: float) -> bool:
        if math.isnan(score) or not (0.0 <= score <= 1.0):
            raise ValueError(f"Invalid score: {score}. Must be in [0.0, 1.0].")
        ...
```

### engine/context.py — Scoped purpose [R6-arch-7]

ExecutionContext is used for ONE purpose in v0.1: **shared state in `pipe()` composition**. When `pipe()` chains patterns, the context carries the accumulated cost tracker so budget enforcement spans all steps. Not used by individual patterns (they are stateless). If context has no consumer, it is cut.

---

## Pattern Base (PUBLIC — `executionkit.patterns.base`) [R6-arch-2]

```python
# patterns/base.py — PUBLIC (no underscore prefix)

def validate_score(score: float) -> float:
    """Validate evaluator output. Raises ValueError on NaN or out-of-range."""
    if math.isnan(score) or not (0.0 <= score <= 1.0):
        raise ValueError(f"Evaluator returned invalid score: {score}")
    return score

async def checked_complete(
    provider: LLMProvider,
    messages: Sequence[dict],
    tracker: CostTracker,
    budget: TokenUsage | None,
    retry: RetryConfig | None,
    **kwargs,
) -> LLMResponse:
    """Provider.complete() with budget check, retry, and truncation detection.
    Budget checked PER-CALL, not per-depth."""
    if budget and tracker.total_tokens >= budget.input_tokens + budget.output_tokens:
        raise BudgetExhaustedError(f"Budget of {budget} exceeded at {tracker.total_tokens} tokens")
    try:
        response = await with_retry(provider.complete, retry or DEFAULT_RETRY, messages, **kwargs)
    except asyncio.CancelledError:
        raise
    tracker.record(response)
    return response
```

Custom pattern authors import these to get the same safety guarantees as built-in patterns.

---

## compose.py — Budget-aware composition [R6-arch-4]

```python
async def pipe(
    provider: LLMProvider,
    prompt: str,
    *steps: PatternStep,
    max_cost: TokenUsage | None = None,
    **shared_kwargs: Any,
) -> PatternResult:
    """Chain patterns sequentially. Output feeds as prompt to next step.
    Costs, traces, and request_ids merge across all steps.
    Budget is shared — remaining budget passed to each step."""
    accumulated = TokenUsage()
    merged_trace: list[TraceEntry] = []
    current_input = prompt
    result: PatternResult | None = None

    try:
        for step_fn in steps:
            remaining = _subtract(max_cost, accumulated) if max_cost else None
            result = await step_fn(provider, current_input, max_cost=remaining, **shared_kwargs)
            current_input = str(result.value)
            accumulated = accumulated + result.cost
            merged_trace.extend(result.trace)
    except (asyncio.CancelledError, PatternError):
        # [R6-eng-5] Preserve partial cost on failure
        if result:
            return PatternResult(
                value=result.value, cost=accumulated, trace=merged_trace,
                metadata={"pipe_interrupted": True},
            )
        raise

    return PatternResult(
        value=result.value, score=result.score,
        cost=accumulated, iterations=len(steps), trace=merged_trace,
    )
```

---

## Pattern Signatures (Post R6)

### tree_of_thought()

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
    max_cost: TokenUsage | None = TokenUsage(500_000, 200_000, 100),
    max_concurrency: int = 10,  # [R6-eng-9] exposed, not hidden
    on_progress: ProgressCallback | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

Uses `gather_resilient`. Failed evaluations score 0.0. Budget per-call via `checked_complete`.

### react_loop()

```python
async def react_loop(
    provider: ToolCallingProvider,  # [R6-arch-1] requires tool support
    prompt: str,
    tools: Sequence[Tool],
    *,
    max_rounds: int = 8,
    max_observation_chars: int = 12000,
    tool_timeout: float | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    on_progress: ProgressCallback | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

Tool execution wrapped in `asyncio.wait_for(tool.execute(), timeout)`. Uses `ToolCallingProvider` not base `LLMProvider`.

### consensus()

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

Uses `gather_strict`. Returns `agreement_ratio` in metadata. Raises `ConsensusFailedError` for `UNANIMOUS` strategy when responses disagree.

### refine_loop()

```python
async def refine_loop(
    provider: LLMProvider,
    prompt: str,
    *,
    evaluator: Evaluator | None = None,
    target_score: float = 0.9,
    max_iterations: int = 5,
    patience: int = 3,           # [R6-eng-10]
    delta_threshold: float = 0.01,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    on_progress: ProgressCallback | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

All evaluator calls go through `validate_score()`. Patience=3 default.

---

## Providers

### _conversion.py (~200-250 LOC) [R6-arch-3, R6-eng-3]

Moved from engine/ to providers/. This is provider-specific, not engine infrastructure.

**Edge cases that MUST be handled (from R6-eng review):**
1. Multiple tool calls in single assistant message
2. Assistant message with tool_calls but null/empty content
3. Tool call ID format differences and ordering preservation
4. Consecutive user/assistant messages (Anthropic requires alternation)
5. System message extraction (Anthropic uses top-level param)
6. Empty tool results (insert placeholder)
7. Unknown content block types (image, etc.) — pass through or raise `UnsupportedContentError`
8. Legacy `function_call` format — reject explicitly
9. `stop_reason` mapping: `end_turn` -> `stop`, `tool_use` -> `tool_calls`, `max_tokens` -> `length`

**Realistic LOC: 200-250.** The earlier 150 LOC estimate was aggressive.

### AnthropicProvider (~120 LOC)

Calls `openai_to_anthropic()` on full message history before each `complete()`. Normalizes response back to `LLMResponse` with `ToolCall` dataclass instances.

### Temperature documentation [R6-eng-8]

All providers document: "Default temperatures are tuned for OpenAI-class models. For smaller local models via Ollama, lower to 0.5-0.7 for coherent output."

---

## Observability [R6-eng-5,6,7]

Every pattern invocation generates a `request_id` (UUID4) at entry. This ID is:
- Set on every `TraceEntry` created during the invocation
- Set on the final `PatternResult.request_id`
- Logged if a structured logger is configured

`TraceEntry` includes:
- `request_id` — correlates all calls in one invocation
- `started_at` — monotonic timestamp for timing analysis
- `duration_ms` — wall-clock time for this step
- `usage` — per-call token breakdown (raw `LLMResponse.usage` dict)

This is sufficient for post-hoc debugging. OpenTelemetry integration deferred to v0.2 for production-grade distributed tracing.

---

## Phased Build Sequence

### Phase 1a: Type Foundation (Day 1)
1. `pyproject.toml` — full metadata, keywords, classifiers, URLs, license
2. `.gitignore`, `LICENSE`, `CHANGELOG.md`, `src/executionkit/py.typed`
3. `provider.py` — LLMProvider + ToolCallingProvider + StreamingProvider (defined, unused) + LLMResponse + ToolCall + full error hierarchy
4. `types.py` — PatternResult, TraceEntry (with request_id, started_at, usage), TokenUsage, Tool, PatternStep Protocol
5. `providers/_mock.py`
6. `tests/conftest.py`

### Phase 1b: Engine (Day 2)
7. Tests first: `test_engine.py`, `test_concurrency.py`
8. `engine/retry.py` — with CancelledError guard
9. `engine/parallel.py` — gather_resilient + gather_strict with ExceptionGroup unwrap
10. `engine/convergence.py` — NaN-safe, patience=3
11. `engine/context.py` — minimal, for pipe() shared state only
12. `engine/json_extraction.py`

### Phase 1c: Providers + Infrastructure (Day 3)
13. Tests first: `test_providers.py`, `test_conversion.py`
14. `providers/_conversion.py` — OpenAI <-> Anthropic (200-250 LOC, all 9 edge cases)
15. `providers/_openai.py`, `_ollama.py`, `_anthropic.py`
16. `providers/__init__.py` — conditional imports
17. `cost.py` — CostTracker
18. `kit.py` — Session class
19. `patterns/base.py` — PUBLIC checked_complete, validate_score

### Phase 2a: Consensus (Day 4)
20. Tests first (including hypothesis)
21. `patterns/consensus.py` with agreement_ratio, ConsensusFailedError

### Phase 2b: Refine Loop (Day 5)
22. Tests first
23. `patterns/refine_loop.py` with NaN guards, patience=3

### Phase 2c: ReAct (Days 6-7)
24. Tests first (multi-turn, tool timeouts, CancelledError)
25. `patterns/react_loop.py` with asyncio.wait_for, ToolCallingProvider

### Phase 2d: Tree of Thought (Days 7-8)
26. Tests first
27. `patterns/tree_of_thought.py` with gather_resilient, default budget, max_concurrency

### Phase 2.5: Composition + Polish (Day 9) [R6-oss]
28. `compose.py` — budget-aware pipe() with partial cost preservation
29. `__init__.py` — exports + Jupyter-safe sync wrappers
30. `__main__.py` — CLI entry point (check/demo/version)
31. Tests: `test_compose.py`, `test_kit.py`

### Phase 3: Launch Readiness (Days 10-12) [R6-oss]
32. README.md — hero example (pipe composition), install, pattern overview
33. Examples — 10 files (see package structure)
34. CONTRIBUTING.md — how to add providers and patterns
35. Google-style docstrings on every public function/class
36. `docs/` — mkdocs-material site auto-generated from docstrings
37. Final: ruff + mypy --strict + pytest --cov-fail-under=80

### Phase 4: v0.2 (DEFER)
- StreamingProvider implementation
- OpenTelemetry integration
- Additional composition operators
- Multi-modal content support in message converter

---

## Stability Policy

- `LLMProvider` Protocol is **frozen for 0.x**. New capabilities via extension Protocols (`ToolCallingProvider`, `StreamingProvider`), not `hasattr()` checks.
- `PatternResult` fields frozen for 0.x. New data goes in `.metadata`.
- `engine/` public API stable for 0.x: RetryConfig, gather_resilient, gather_strict, ConvergenceDetector, with_retry.
- `patterns.base` public API stable for 0.x: checked_complete, validate_score.
- SemVer: 0.x allows breaking changes between minors. 1.0 locks the public API.

---

## Hero Example (README)

```python
from executionkit import pipe, refine_loop, consensus
from executionkit.providers import OpenAIProvider

provider = OpenAIProvider("gpt-4o-mini")

# Draft an analysis, improve it, then verify with multiple samples
result = await pipe(
    provider,
    "Analyze this contract clause for legal risks: ...",
    refine_loop,   # Self-improve until quality converges
    consensus,     # Cross-check with 5 independent samples
)

print(result.value)                          # The verified analysis
print(result.cost)                           # Total tokens across BOTH steps
print(result.metadata["agreement_ratio"])    # 0.8 = 4 of 5 agreed
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Cost explosion** | Default max_cost on ToT (100 calls). Per-call budget via checked_complete(). BudgetExhaustedError raised. pipe() passes remaining budget to each step. |
| **Partial failures** | gather_resilient returns exceptions as values. Failed evals = 0.0. |
| **Tool hangs** | asyncio.wait_for with Tool.timeout (default 30s). |
| **NaN scores** | validate_score raises immediately. ConvergenceDetector validates on entry. |
| **Anthropic format** | Dedicated _conversion.py (200-250 LOC). 9 edge cases handled. Round-trip tested. |
| **CancelledError** | with_retry never retries on cancellation. gather_resilient propagates it. |
| **ExceptionGroup** | gather_strict unwraps single exceptions. Multi-exception groups propagate. |
| **Pipe interruption** | try/finally preserves partial costs. Returns partial PatternResult. |
| **Paradigm lock-in** | Stateless functions. Extension Protocols for evolution. |
| **Jupyter** | nest_asyncio detection + clear error message. |
| **Custom patterns** | engine/ and patterns.base are public. Same infrastructure as built-ins. |
| **Protocol evolution** | ToolCallingProvider and StreamingProvider defined now. Additive, not breaking. |

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

---

## Verification

1. `ruff check src/executionkit` — passes
2. `ruff format --check src/executionkit` — passes
3. `mypy --strict src/executionkit` — passes
4. `pytest tests/ -m "not integration" --cov=executionkit --cov-fail-under=80` — passes
5. `executionkit demo` — CLI runs with MockProvider, zero config
6. `examples/quickstart_openai.py` — works with OPENAI_API_KEY
7. `examples/quickstart_ollama.py` — works with local Ollama
8. `examples/quickstart_notebook.ipynb` — works in Jupyter
9. `examples/compose_pipeline.py` — pipe() merges costs correctly
10. `examples/classification.py` — consensus with agreement_ratio
11. `examples/structured_extraction.py` — refine_loop with Pydantic
12. `examples/error_handling.py` — BudgetExhaustedError, timeouts
13. `mkdocs serve` — docs site renders from docstrings
