# ExecutionKit — Implementation Plan

Composable LLM reasoning patterns. Python 3.11+. Zero SDK dependencies.

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

The core insight: **almost every LLM provider now speaks OpenAI-compatible `/chat/completions`**. OpenAI, Azure, GitHub Models, Ollama, vLLM, LiteLLM, Together, Groq, Fireworks, Anyscale — all accept the same JSON format.

One provider class. stdlib `urllib` + `asyncio.to_thread`. Zero pip dependencies beyond pydantic.

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
        payload.update(kwargs)  # response_format, seed, etc.

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
                arguments=json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
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

**What this eliminates:**
- `openai` SDK dependency (~5MB, version churn)
- `anthropic` SDK dependency
- All SDK-specific error mapping
- The entire `_conversion.py` (200-250 LOC)
- Separate `_openai.py`, `_ollama.py`, `_anthropic.py` files
- The `providers/` subdirectory entirely

**What about Anthropic?** Anthropic doesn't speak OpenAI format. For v0.1, users who want Anthropic can either: (a) run it through a LiteLLM proxy (1 line: `litellm --model claude-sonnet-4-20250514`), or (b) implement the `LLMProvider` Protocol themselves (~60 LOC). Native Anthropic support is a v0.2 feature when demand proves it.

---

## Package Structure

```
src/executionkit/
  __init__.py             # Public exports + sync wrappers
  py.typed
  provider.py             # Provider class + LLMResponse + ToolCall + errors
  types.py                # PatternResult[T], TokenUsage, Tool, Evaluator
  cost.py                 # CostTracker
  engine/                 # PUBLIC — custom patterns reuse these
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

**Dependencies:**
```toml
[project]
dependencies = ["pydantic>=2.0,<3"]
# That's it. Zero SDK deps. Provider uses stdlib urllib.
```

---

## provider.py — Types & Errors

```python
# Protocol (for users who want to bring their own provider)
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

# Errors
class ExecutionKitError(Exception): ...
class LLMError(ExecutionKitError): ...
class RateLimitError(LLMError): ...      # Retryable
class PermanentError(LLMError): ...      # Auth, not-found — NOT retried
class ProviderError(LLMError): ...       # Catch-all retryable
class PatternError(ExecutionKitError): ...
class BudgetExhaustedError(PatternError): ...
class ConsensusFailedError(PatternError): ...
class MaxIterationsError(PatternError): ...
```

---

## types.py

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
        """OpenAI function-calling format."""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters,
        }}

class VotingStrategy(str, Enum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"

Evaluator: TypeAlias = Callable[[str, LLMProvider], Awaitable[float]]
```

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

Budget is a **soft cap** — checked BEFORE each call, response tokens counted AFTER.

---

## engine/

### parallel.py

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

### retry.py

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

DEFAULT_RETRY = RetryConfig()

async def with_retry(fn: Callable[..., Awaitable[T]], config: RetryConfig, *args, **kwargs) -> T:
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

### convergence.py

```python
@dataclass
class ConvergenceDetector:
    delta_threshold: float = 0.01
    patience: int = 3
    score_threshold: float | None = None

    def should_stop(self, score: float) -> bool:
        if math.isnan(score) or not (0.0 <= score <= 1.0):
            raise ValueError(f"Invalid score: {score}")
        # ... delta tracking, stale count, patience check
```

---

## patterns/base.py (PUBLIC)

```python
def validate_score(score: float) -> float:
    if math.isnan(score) or not (0.0 <= score <= 1.0):
        raise ValueError(f"Invalid evaluator score: {score}")
    return score

async def checked_complete(
    provider: LLMProvider, messages: Sequence[dict], tracker: CostTracker,
    budget: TokenUsage | None, retry: RetryConfig | None, **kwargs,
) -> LLMResponse:
    """Budget check → retry-wrapped complete() → record usage."""
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

## Sync Wrappers (Jupyter-safe)

```python
def _run_sync(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        try:
            import nest_asyncio; nest_asyncio.apply()
            return loop.run_until_complete(coro)
        except ImportError:
            raise RuntimeError("Install nest_asyncio for Jupyter: pip install nest_asyncio")
    return asyncio.run(coro)
```

---

## Phased Build Sequence

### Phase 1: Foundation (Days 1-2)
1. `pyproject.toml`, `.gitignore`, `LICENSE`, `CHANGELOG.md`, `py.typed`
2. `provider.py` — Provider class, LLMProvider Protocol, LLMResponse, ToolCall, all errors
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
12. Tests first → `patterns/consensus.py`
13. Tests first → `patterns/refine_loop.py`
14. Tests first → `patterns/react_loop.py`

### Phase 3: Polish (Days 7-8)
15. `__init__.py` — exports + sync wrappers
16. 5 examples: quickstart_openai, quickstart_ollama, classification, compose, error_handling
17. README.md
18. Final: ruff + mypy --strict + pytest --cov-fail-under=80

### Phase 4: v0.2 (DEFER)
- tree_of_thought (beam search)
- pipe() composition
- Anthropic native provider
- Streaming support
- OpenTelemetry

---

## Test Strategy

**Categories:** unit (MockProvider), edge cases, property-based (hypothesis), concurrency, integration (skipped in CI).

**Coverage:** 80% overall, 90% patterns/.

**CI:** Ubuntu + Windows, Python 3.11/3.12/3.13. ruff → mypy --strict → pytest.

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
| Non-OpenAI providers | LLMProvider Protocol lets users bring their own. |

---

## Verification

1. `ruff check` + `mypy --strict` — all pass
2. `pytest --cov-fail-under=80` — all pass
3. `examples/quickstart_openai.py` — works with OPENAI_API_KEY
4. `examples/quickstart_ollama.py` — works locally, zero cloud deps
5. `examples/classification.py` — consensus with agreement_ratio
6. `examples/error_handling.py` — BudgetExhaustedError, timeouts
