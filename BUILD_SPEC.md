# ExecutionKit v0.1 — Build Specification

> Historical build artifact for the original v0.1 scope. Current code in
> `/home/runner/work/executionkit/executionkit/executionkit/` is authoritative
> when this document conflicts with the implementation.

Single source of truth for building. Consolidates PLAN_SIMPLE.md + FINAL_VERDICT.md + all iteration fixes.

**Start here. Don't read anything else until you need historical context (see `planning/`).**

---

## Positioning

ExecutionKit is a minimal Python library for composable LLM reasoning patterns. It fills the gap between raw chat calls and full orchestration stacks — more power than one-off prompts, less weight than a framework.

**What ExecutionKit IS:**
- A pattern library, not a full agent platform
- An execution layer, not a gateway or proxy
- A budget-aware composition toolkit, not an observability suite
- A portable OpenAI-compatible client, not a native adapter matrix

**What ExecutionKit is NOT:**
- Not a LangGraph-style stateful graph runtime for durable workflows
- Not a PydanticAI-style full agent framework with broad provider-native support
- Not a LiteLLM-style gateway/proxy with spend dashboards and routing
- Not an OpenAI Agents SDK-style multi-agent orchestration package

**Messaging — lead with:** composable reasoning patterns, budget-aware execution, OpenAI-compatible portability, minimal dependencies

**Messaging — de-emphasize:** "universal provider", "supports many endpoints", "agent orchestration", "framework", "gateway"

### Anti-Scope Guardrails

Three creep zones to reject at all times:

1. **Platform creep:** dashboards, routing/fallback matrices, tenancy, keys, quotas, governance, observability platform positioning
2. **Framework creep:** stateful graphs, memory runtimes, durable execution, resumability, multi-agent handoff
3. **Provider-matrix creep:** native Anthropic in core, adapter sprawl, "supports everything" messaging

---

## What Ships in v0.1

| Category | Items |
|----------|-------|
| **Patterns** | consensus, refine_loop, react_loop |
| **Composition** | pipe() |
| **Session** | Kit |
| **Provider** | Single `Provider` class (URL + API key + model) |
| **Engine** | retry, parallel, convergence, json_extraction |
| **Types** | PatternResult[T], TokenUsage, Tool, ToolCall, VotingStrategy (MAJORITY/UNANIMOUS), Evaluator, LLMResponse |
| **Errors** | 9 classes (ExecutionKitError > LLMError > RateLimitError/PermanentError/ProviderError, ExecutionKitError > PatternError > BudgetExhaustedError/ConsensusFailedError/MaxIterationsError) |
| **Features** | CostTracker, checked_complete, validate_score, agreement_ratio, was_truncated, ConvergenceDetector |
| **Infrastructure** | pyproject.toml, 5 examples, README, CONTRIBUTING.md |

**Estimated:** ~1,700 LOC, 7-8 days

## What Defers to v0.2

- tree_of_thought (beam search — most complex, academic)
- Anthropic native provider + message converter
- TraceEntry + ProgressCallback (observability)
- StreamingProvider
- OpenTelemetry
- Astro/MkDocs documentation unification work

---

## Hero Example

```python
from executionkit import consensus, Provider

provider = Provider("https://api.openai.com/v1", api_key="sk-...", model="gpt-4o-mini")

result = await consensus(provider, "Classify this support ticket: ...", num_samples=5)
print(result)                                # The classification
print(result.cost)                           # TokenUsage(input_tokens=250, output_tokens=45, llm_calls=5)
print(result.metadata["agreement_ratio"])    # 0.8 = 4 of 5 agreed
```

```python
# Works with ANY OpenAI-compatible endpoint — zero config change
ollama   = Provider("http://localhost:11434/v1", model="llama3.2")
github   = Provider("https://models.inference.ai.azure.com", api_key=GITHUB_TOKEN, model="gpt-4o-mini")
together = Provider("https://api.together.xyz/v1", api_key=TOGETHER_KEY, model="meta-llama/Llama-3-70b")
groq     = Provider("https://api.groq.com/openai/v1", api_key=GROQ_KEY, model="llama-3.3-70b")
```

---

## The Provider: URL + API Key + JSON

Core insight: almost every LLM provider speaks OpenAI-compatible `/chat/completions`. One class, stdlib `urllib` + optional `httpx`, zero required runtime dependencies.

```python
@dataclass
class Provider:
    """Universal LLM provider. Posts JSON, parses JSON. No SDK needed."""
    base_url: str                         # "https://api.openai.com/v1"
    model: str                            # "gpt-4o-mini"
    api_key: str = ""                     # Optional (Ollama doesn't need one)
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    timeout: float = 120.0

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """POST to {base_url}/chat/completions, parse JSON response."""
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
        }
        if tools:
            payload["tools"] = list(tools)
        payload.update(kwargs)  # response_format, seed, top_p, etc.
        data = await self._post("chat/completions", payload)
        return self._parse_response(data)

    async def _post(self, endpoint: str, payload: dict) -> dict:
        """HTTP POST via stdlib urllib in a thread."""
        import json, urllib.request
        url = f"{self.base_url.rstrip('/')}/{endpoint}"
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        def _sync():
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.status
                raw = json.loads(resp.read())
                if status == 429:
                    raise RateLimitError("Rate limited", retry_after=float(resp.headers.get("retry-after", 1)))
                if status == 401:
                    raise PermanentError("Authentication failed")
                if status >= 400:
                    raise ProviderError(f"HTTP {status}: {raw}")
                return raw

        return await asyncio.to_thread(_sync)

    def _parse_response(self, data: dict) -> LLMResponse:
        choice = data["choices"][0]
        msg = choice["message"]
        usage = data.get("usage", {})
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"]["arguments"])
                    if isinstance(tc["function"]["arguments"], str)
                    else tc["function"]["arguments"],
            )
            for tc in (msg.get("tool_calls") or [])
        ]
        return LLMResponse(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=usage,
            raw=data,
        )
```

**Sampling params:** `temperature` is explicit. `top_p`, `top_k`, `seed`, `response_format` go through `**kwargs` into the payload. This works for all OpenAI-compatible endpoints. Ollama's compat layer (`/v1/chat/completions`) accepts them at the top level too.

---

## Package Structure

```
executionkit/
  __init__.py             # Public exports + sync wrappers
  py.typed
  provider.py             # Provider class + LLMResponse + ToolCall + errors
  types.py                # PatternResult[T], TokenUsage, Tool, Evaluator, VotingStrategy
  cost.py                 # CostTracker
  compose.py              # pipe()
  kit.py                  # Kit session
  engine/
    __init__.py
    retry.py              # RetryConfig + with_retry()
    parallel.py           # gather_resilient + gather_strict
    convergence.py        # ConvergenceDetector
    json_extraction.py    # Balanced-brace JSON fallback (for Ollama)
  patterns/
    __init__.py
    base.py               # checked_complete, validate_score
    consensus.py
    refine_loop.py
    react_loop.py
  _mock.py                # MockProvider for testing
tests/
examples/
```

**Dependencies:** none required at runtime. `httpx` is optional for pooled HTTP.

---

## Types (types.py)

```python
@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    def __add__(self, other: TokenUsage) -> TokenUsage: ...

@dataclass(frozen=True, slots=True)
class PatternResult(Generic[T]):
    value: T
    score: float | None = None
    cost: TokenUsage = field(default_factory=TokenUsage)
    metadata: dict[str, Any] = field(default_factory=dict)
    def __str__(self) -> str: return str(self.value)

@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    execute: Callable[..., Awaitable[str]]
    timeout: float = 30.0
    def to_schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters,
        }}

class VotingStrategy(str, Enum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"

Evaluator: TypeAlias = Callable[[str, LLMProvider], Awaitable[float]]
```

## Provider Types (provider.py)

```python
@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self, messages: Sequence[dict[str, Any]], *,
        temperature: float | None = None, max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None, **kwargs: Any,
    ) -> LLMResponse: ...

@dataclass(frozen=True, slots=True)
class ToolCall:
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
    def input_tokens(self) -> int:
        u = self.usage
        return int(u.get("input_tokens", 0) or u.get("prompt_tokens", 0))
    @property
    def output_tokens(self) -> int:
        u = self.usage
        return int(u.get("output_tokens", 0) or u.get("completion_tokens", 0))
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    @property
    def has_tool_calls(self) -> bool: return bool(self.tool_calls)
    @property
    def was_truncated(self) -> bool: return self.finish_reason == "length"
```

## Error Hierarchy (provider.py)

```
ExecutionKitError
  LLMError
    RateLimitError        (retryable)
    PermanentError        (auth, not-found — NOT retried)
    ProviderError         (catch-all retryable)
  PatternError
    BudgetExhaustedError
    ConsensusFailedError
    MaxIterationsError
```

9 classes total. PermanentError prevents auth failures from retrying 3x.

---

## Engine Modules

### engine/retry.py

```python
@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable: tuple[type[Exception], ...] = (RateLimitError, ProviderError)

    def should_retry(self, exc: Exception) -> bool:
        return isinstance(exc, self.retryable)
    def get_delay(self, attempt: int) -> float:
        return min(self.base_delay * (self.exponential_base ** (attempt - 1)), self.max_delay)

T = TypeVar("T")
DEFAULT_RETRY = RetryConfig()

async def with_retry(fn, config, *args, **kwargs) -> T:
    if config.max_retries == 0:
        return await fn(*args, **kwargs)
    for attempt in range(1, config.max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not config.should_retry(exc) or attempt == config.max_retries:
                raise
            await asyncio.sleep(config.get_delay(attempt))
    raise RuntimeError("unreachable")
```

### engine/parallel.py

```python
async def gather_resilient(coros, max_concurrency=10) -> list[Any | BaseException]:
    """Returns exceptions as values. CancelledError propagates."""
    semaphore = asyncio.Semaphore(max_concurrency)
    async def run(coro):
        async with semaphore:
            return await coro
    try:
        return await asyncio.gather(*[run(c) for c in coros], return_exceptions=True)
    except asyncio.CancelledError:
        raise

async def gather_strict(coros, max_concurrency=10) -> list[Any]:
    """All-or-nothing. Single exceptions unwrapped from ExceptionGroup."""
    semaphore = asyncio.Semaphore(max_concurrency)
    results = [None] * len(coros)
    async def run(i, coro):
        async with semaphore:
            results[i] = await coro
    try:
        async with asyncio.TaskGroup() as tg:
            for i, coro in enumerate(coros):
                tg.create_task(run(i, coro))
    except ExceptionGroup as eg:
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from eg
        raise
    return results
```

### engine/convergence.py

```python
@dataclass
class ConvergenceDetector:
    delta_threshold: float = 0.01
    patience: int = 3
    score_threshold: float | None = None

    def should_stop(self, score: float) -> bool:
        if math.isnan(score) or not (0.0 <= score <= 1.0):
            raise ValueError(f"Invalid score: {score}")
        # Track delta, stale count, patience
```

### engine/json_extraction.py

Balanced-brace JSON extraction fallback for Ollama models that don't enforce `response_format`.

---

## Pattern Signatures

### consensus()

```python
async def consensus(
    provider: LLMProvider, prompt: str, *,
    num_samples: int = 5, strategy: VotingStrategy | str = "majority",
    temperature: float = 0.9, max_tokens: int = 4096,
    max_concurrency: int = 5, retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

Uses `gather_strict`. Metadata: `agreement_ratio`, `unique_responses`, `tie_count`.

### refine_loop()

```python
async def refine_loop(
    provider: LLMProvider, prompt: str, *,
    evaluator: Evaluator | None = None, target_score: float = 0.9,
    max_iterations: int = 5, patience: int = 3, delta_threshold: float = 0.01,
    temperature: float = 0.7, max_tokens: int = 4096,
    max_cost: TokenUsage | None = None, retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

Uses ConvergenceDetector. Default evaluator asks LLM to score 0-10.

### react_loop()

```python
async def react_loop(
    provider: LLMProvider, prompt: str, tools: Sequence[Tool], *,
    max_rounds: int = 8, max_observation_chars: int = 12000,
    tool_timeout: float | None = None,
    temperature: float = 0.3, max_tokens: int = 4096,
    max_cost: TokenUsage | None = None, retry: RetryConfig | None = None,
) -> PatternResult[str]:
```

Tool execution wrapped in `asyncio.wait_for(tool.execute(), timeout)`.

---

## cost.py

```python
class CostTracker:
    def __init__(self) -> None:
        self._input: int = 0
        self._output: int = 0
        self._calls: int = 0

    def record(self, response: LLMResponse) -> None:
        self._input += response.input_tokens
        self._output += response.output_tokens
        self._calls += 1

    @property
    def total_tokens(self) -> int: return self._input + self._output
    def to_usage(self) -> TokenUsage: return TokenUsage(self._input, self._output, self._calls)
```

## patterns/base.py

```python
def validate_score(score: float) -> float:
    if math.isnan(score) or not (0.0 <= score <= 1.0):
        raise ValueError(f"Invalid evaluator score: {score}")
    return score

async def checked_complete(
    provider: LLMProvider, messages: Sequence[dict], tracker: CostTracker,
    budget: TokenUsage | None, retry: RetryConfig | None, **kwargs,
) -> LLMResponse:
    """Budget check -> retry-wrapped complete() -> record usage."""
    if budget and (tracker.total_tokens >= budget.input_tokens + budget.output_tokens
                   or tracker._calls >= budget.llm_calls > 0):
        raise BudgetExhaustedError(...)
    try:
        response = await with_retry(provider.complete, retry or DEFAULT_RETRY, messages, **kwargs)
    except asyncio.CancelledError:
        raise
    tracker.record(response)
    return response
```

---

## compose.py — pipe()

```python
async def pipe(
    provider: LLMProvider, prompt: str, *steps: Callable,
    max_budget: TokenUsage | None = None,
    **shared_kwargs: Any,
) -> PatternResult:
    """Chain patterns. Output of step N -> prompt to step N+1.
    Costs merge. Budget shared (remaining passed to each step)."""
    if not steps:
        return PatternResult(value=prompt)
    # _subtract() helper: remaining = max_budget - used_so_far (clamped to 0)
```

---

## Phased Build Sequence

### Phase 1: Foundation (Days 1-2)
1. `pyproject.toml`, `.gitignore`, `LICENSE`, `CHANGELOG.md`, `py.typed`
2. `provider.py` — Provider class, LLMProvider Protocol, LLMResponse, ToolCall, all 9 errors
3. `types.py` — PatternResult, TokenUsage, Tool, VotingStrategy, Evaluator
4. `_mock.py` — MockProvider
5. `cost.py` — CostTracker
6. `engine/retry.py` — RetryConfig, with_retry, DEFAULT_RETRY
7. `engine/parallel.py` — gather_resilient, gather_strict
8. `engine/convergence.py` — ConvergenceDetector
9. `engine/json_extraction.py` — balanced-brace fallback
10. `patterns/base.py` — checked_complete, validate_score
11. `tests/` — conftest, test_provider, test_engine, test_concurrency

### Phase 2: Patterns (Days 3-6)
12. Tests first -> `patterns/consensus.py`
13. Tests first -> `patterns/refine_loop.py`
14. Tests first -> `patterns/react_loop.py`

### Phase 3: Composition + Polish (Days 7-8)
15. `compose.py` — pipe()
16. `kit.py` — Kit session
17. `__init__.py` — exports + sync wrappers
18. 5 examples
19. README.md, CONTRIBUTING.md
20. Final: ruff + mypy --strict + pytest --cov-fail-under=80

---

## Pre-Build Checklist (Day 1 morning)

All 5 blockers from iteration 1 are resolved in the code sketches above. Verify during implementation:

- [ ] `_subtract()` in compose.py uses `max(0, ...)` clamping
- [ ] pipe() guards empty steps: `if not steps: return PatternResult(value=prompt)`
- [ ] RetryConfig has full class with `should_retry()` + `get_delay()`
- [ ] `T = TypeVar("T")` in retry.py
- [ ] `with_retry` has `max_retries=0` guard (direct call, no retry loop)
- [ ] `Evaluator: TypeAlias = Callable[...]` (not bare assignment)
- [ ] All `PatternResult` uses include type param: `PatternResult[Any]` or `PatternResult[str]`
- [ ] CancelledError guards in with_retry and checked_complete
- [ ] Error hierarchy: 9 classes, PermanentError under LLMError
- [ ] VotingStrategy is an enum (MAJORITY + UNANIMOUS), not a string

---

## Verification Gates

```bash
# Code quality
ruff check . && ruff format . --check
mypy --strict src/

# Tests
pytest --cov-fail-under=80 -m "not integration"

# Smoke tests
OPENAI_API_KEY=sk-... python examples/quickstart_openai.py
python examples/quickstart_ollama.py  # requires local Ollama

# Security
# Zero hardcoded secrets, .env in .gitignore, no API keys in code
```

---

## Test Strategy

- **Unit:** MockProvider, test voting logic, convergence, retry, budget tracking
- **Edge cases:** Tie resolution, NaN scores, empty results, CancelledError
- **Concurrency:** Semaphore limits, gather_strict exception unwrapping
- **Integration:** Real API calls (marked `@pytest.mark.integration`, skipped in CI)
- **Coverage:** 80% overall, 90% patterns/
- **CI:** Ubuntu + Windows, Python 3.11/3.12/3.13

---

## 90-Day Kill Condition

<50 GitHub stars AND zero production evidence -> archive the project.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Cost explosion | Per-call budget via checked_complete(). BudgetExhaustedError. |
| Partial failures | gather_resilient returns exceptions as values. |
| Tool hangs | asyncio.wait_for with Tool.timeout (default 30s). |
| NaN scores | validate_score raises immediately. |
| Jupyter | nest_asyncio detection + clear error. |
| Provider compat | OpenAI-compatible JSON format covers 90%+ of providers. |
| Non-OpenAI (Anthropic) | LLMProvider Protocol lets users implement their own. LiteLLM proxy as stopgap. |
| Auth retry loops | PermanentError (under LLMError) is NOT retried. |

---

## Historical Context

All planning artifacts are in `planning/`. Reference only if you need to understand WHY a decision was made:

| File | What It Contains |
|------|-----------------|
| `PLAN.md` | Original 1,021-line plan (6 rounds of review) |
| `PLAN_SIMPLE.md` | Simplified plan (predecessor to this BUILD_SPEC) |
| `FINAL_VERDICT.md` | 3-iteration review synthesis, GO decision |
| `REVIEW_ITERATION_*.md` | Market/technical/scope reviews |
| `REVIEW_AUDIT.md` | Traceability matrix for all issues |
| `MVP_*.md`, `SHIP_DECISION.md`, etc. | Pre-iteration-2 tier analysis (STALE — several decisions reversed) |
