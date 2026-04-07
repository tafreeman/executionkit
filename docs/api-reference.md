# ExecutionKit API Reference

Version: **0.1.0** | Requires Python 3.11+

---

## Quick Reference

| Symbol | Kind | Description |
|---|---|---|
| `consensus()` | function | Parallel sampling with majority or unanimous voting |
| `consensus_sync()` | function | Synchronous wrapper for `consensus()` |
| `refine_loop()` | function | Iterative refinement with convergence detection |
| `refine_loop_sync()` | function | Synchronous wrapper for `refine_loop()` |
| `react_loop()` | function | Think-act-observe tool-calling loop |
| `react_loop_sync()` | function | Synchronous wrapper for `react_loop()` |
| `pipe()` | function | Chain patterns, threading output as next prompt |
| `pipe_sync()` | function | Synchronous wrapper for `pipe()` |
| `Kit` | class | Session wrapper holding a provider and tracking cumulative usage |
| `Provider` | class | Universal OpenAI-compatible HTTP provider |
| `MockProvider` | class | Test double implementing `LLMProvider` |
| `PatternResult[T]` | dataclass | Return type for every pattern |
| `TokenUsage` | dataclass | Accumulated token and call counts |
| `Tool` | dataclass | Tool definition for LLM tool-calling |
| `LLMResponse` | dataclass | Parsed LLM completion response |
| `ToolCall` | dataclass | Single tool invocation from an LLM response |
| `LLMProvider` | protocol | Structural protocol for any LLM backend |
| `ToolCallingProvider` | protocol | Extension of `LLMProvider` for tool-calling backends |
| `VotingStrategy` | enum | `MAJORITY` or `UNANIMOUS` |
| `Evaluator` | type alias | `async (str, LLMProvider) -> float` |
| `PatternStep` | protocol | Callable protocol for `pipe()` steps |
| `RetryConfig` | dataclass | Immutable retry configuration |
| `DEFAULT_RETRY` | constant | Default `RetryConfig` instance |
| `ConvergenceDetector` | class | Tracks score history for convergence detection |
| `CostTracker` | class | Mutable accumulator for token and call counts |
| `extract_json()` | function | Robust JSON extraction from LLM output |
| `checked_complete()` | function | Budget-checked, retry-wrapped `complete()` |
| `validate_score()` | function | Validate evaluator score is in [0.0, 1.0] |
| `ExecutionKitError` | exception | Base exception class |
| `LLMError` | exception | Provider communication errors |
| `RateLimitError` | exception | HTTP 429 rate limit (has `retry_after`) |
| `PermanentError` | exception | Non-retryable provider error |
| `ProviderError` | exception | Retryable catch-all provider error |
| `PatternError` | exception | Pattern logic errors |
| `BudgetExhaustedError` | exception | Token or call budget exceeded |
| `ConsensusFailedError` | exception | Consensus could not reach agreement |
| `MaxIterationsError` | exception | Loop exceeded its iteration limit |

---

## Patterns

### `consensus()`

```python
async def consensus(
    provider: LLMProvider,
    prompt: str,
    *,
    num_samples: int = 5,
    strategy: VotingStrategy | str = "majority",
    temperature: float = 0.9,
    max_tokens: int = 4096,
    max_concurrency: int = 5,
    retry: RetryConfig | None = None,
) -> PatternResult[str]
```

Fires `num_samples` concurrent completions and selects the winning response via voting.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider` | `LLMProvider` | required | LLM provider to call |
| `prompt` | `str` | required | User prompt sent identically to every sample |
| `num_samples` | `int` | `5` | Number of parallel completions to request |
| `strategy` | `VotingStrategy \| str` | `"majority"` | `"majority"` (most common wins) or `"unanimous"` (all must agree) |
| `temperature` | `float` | `0.9` | Sampling temperature; higher values produce more diverse responses |
| `max_tokens` | `int` | `4096` | Maximum tokens per completion |
| `max_concurrency` | `int` | `5` | Semaphore limit for concurrent calls |
| `retry` | `RetryConfig \| None` | `None` | Retry configuration per call; uses `DEFAULT_RETRY` if `None` |

**Returns:** `PatternResult[str]`

- `value`: The winning response string
- `score`: Agreement ratio (0.0–1.0); equal to `metadata["agreement_ratio"]`
- `cost`: Accumulated `TokenUsage` across all samples
- `metadata`: See keys below

**Metadata keys:**

| Key | Type | Description |
|---|---|---|
| `agreement_ratio` | `float` | Fraction of samples matching the winner (0.0–1.0) |
| `unique_responses` | `int` | Number of distinct response strings observed |
| `tie_count` | `int` | Number of responses that tied for the top vote count |

**Raises:**

- `ConsensusFailedError` — when `strategy="unanimous"` and responses are not all identical
- `RateLimitError`, `PermanentError`, `ProviderError` — from the underlying provider

**Example:**

```python
from executionkit import Provider, consensus

result = await consensus(
    provider,
    "Classify as POSITIVE, NEGATIVE, or NEUTRAL: 'Great product!'",
    num_samples=5,
    strategy="majority",
)
print(result.value)                              # "POSITIVE"
print(f"{result.metadata['agreement_ratio']:.0%}")  # "80%"
```

---

### `consensus_sync()`

```python
def consensus_sync(
    provider: LLMProvider,
    prompt: str,
    **kwargs: Any,
) -> PatternResult[str]
```

Synchronous wrapper for `consensus()`. Accepts all the same keyword arguments.

Raises `RuntimeError` if called from within an already-running event loop (e.g., inside Jupyter). Use `await consensus(...)` instead, or apply `nest_asyncio` first.

---

### `refine_loop()`

```python
async def refine_loop(
    provider: LLMProvider,
    prompt: str,
    *,
    evaluator: Evaluator | None = None,
    target_score: float = 0.9,
    max_iterations: int = 5,
    patience: int = 3,
    delta_threshold: float = 0.01,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[str]
```

Generates an initial response, evaluates it, then iteratively refines it until convergence or the iteration budget is exhausted.

Each iteration sends the previous response and its score back to the LLM with a request to improve it. The loop terminates when `ConvergenceDetector` signals convergence (target score reached or score deltas stall for `patience` iterations) or `max_iterations` is exhausted.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider` | `LLMProvider` | required | LLM provider to call |
| `prompt` | `str` | required | The original user prompt |
| `evaluator` | `Evaluator \| None` | `None` | Async callable `(text, provider) -> float` returning a score in [0.0, 1.0]. If `None`, a built-in LLM-based evaluator is used |
| `target_score` | `float` | `0.9` | Convergence target in [0.0, 1.0] |
| `max_iterations` | `int` | `5` | Maximum refinement iterations (excluding the initial generation) |
| `patience` | `int` | `3` | Stale-delta iterations before convergence is declared |
| `delta_threshold` | `float` | `0.01` | Minimum meaningful score improvement between iterations |
| `temperature` | `float` | `0.7` | Sampling temperature for generation calls |
| `max_tokens` | `int` | `4096` | Maximum tokens per completion |
| `max_cost` | `TokenUsage \| None` | `None` | Optional token/call budget across all calls |
| `retry` | `RetryConfig \| None` | `None` | Retry configuration per call; uses `DEFAULT_RETRY` if `None` |

**Returns:** `PatternResult[str]`

- `value`: The best response seen across all iterations
- `score`: Evaluation score of the best response (0.0–1.0)
- `cost`: Accumulated `TokenUsage` across all calls (generation + evaluation)
- `metadata`: See keys below

**Metadata keys:**

| Key | Type | Description |
|---|---|---|
| `iterations` | `int` | Refinement iterations performed (0 means converged on first attempt) |
| `converged` | `bool` | Whether the loop converged before reaching `max_iterations` |
| `score_history` | `list[float]` | Score at each iteration, including the initial generation |

**Raises:**

- `BudgetExhaustedError` — when `max_cost` is exceeded before a call
- `MaxIterationsError` — not raised by `refine_loop`; it returns after `max_iterations` even if not converged
- `RateLimitError`, `PermanentError`, `ProviderError` — from the underlying provider

**Default evaluator — security note:**

When `evaluator=None`, the built-in evaluator wraps the response text in XML delimiters (`<response_to_rate>...</response_to_rate>`) before sending it to the LLM for scoring. This sandboxing prevents adversarial content inside the response from overriding the scoring instruction (prompt injection mitigation). The evaluator also truncates input to 32,768 characters.

**Example:**

```python
from executionkit import Provider, refine_loop

result = await refine_loop(
    provider,
    "Explain recursion in one paragraph.",
    target_score=0.85,
    max_iterations=3,
)
print(result.value)
print(f"Score: {result.score:.2f}, iterations: {result.metadata['iterations']}")
```

**Custom evaluator example:**

```python
from executionkit.provider import LLMProvider

async def word_count_evaluator(text: str, llm: LLMProvider) -> float:
    words = len(text.split())
    return min(1.0, words / 100)  # target 100+ words

result = await refine_loop(provider, prompt, evaluator=word_count_evaluator)
```

---

### `refine_loop_sync()`

```python
def refine_loop_sync(
    provider: LLMProvider,
    prompt: str,
    **kwargs: Any,
) -> PatternResult[str]
```

Synchronous wrapper for `refine_loop()`. Accepts all the same keyword arguments.

Raises `RuntimeError` if called from within an already-running event loop.

---

### `react_loop()`

```python
async def react_loop(
    provider: ToolCallingProvider,
    prompt: str,
    tools: Sequence[Tool],
    *,
    max_rounds: int = 8,
    max_observation_chars: int = 12000,
    tool_timeout: float | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
    max_history_messages: int | None = None,
) -> PatternResult[str]
```

Executes a think-act-observe tool-calling loop. The LLM is called repeatedly with the conversation history and available tool schemas. When the LLM returns tool calls, each tool is executed and its result appended as a `tool` role message. The loop ends when the LLM responds without tool calls (final answer) or `max_rounds` is exhausted.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider` | `ToolCallingProvider` | required | LLM provider with tool-calling support |
| `prompt` | `str` | required | Initial user prompt |
| `tools` | `Sequence[Tool]` | required | Tool definitions available to the LLM |
| `max_rounds` | `int` | `8` | Maximum think-act-observe cycles |
| `max_observation_chars` | `int` | `12000` | Truncation limit for each individual tool result |
| `tool_timeout` | `float \| None` | `None` | Per-call timeout override; falls back to `tool.timeout` if `None` |
| `temperature` | `float` | `0.3` | Sampling temperature (lower = more deterministic) |
| `max_tokens` | `int` | `4096` | Maximum tokens per LLM completion |
| `max_cost` | `TokenUsage \| None` | `None` | Optional token/call budget |
| `retry` | `RetryConfig \| None` | `None` | Retry configuration per LLM call; uses `DEFAULT_RETRY` if `None` |
| `max_history_messages` | `int \| None` | `None` | When set, trims the message history to at most this many entries before each LLM call, always preserving the original prompt |

**Returns:** `PatternResult[str]`

- `value`: Final LLM response (the text answer after all tool calls are resolved)
- `score`: Always `None`
- `cost`: Accumulated `TokenUsage` across all LLM calls
- `metadata`: See keys below

**Metadata keys:**

| Key | Type | Description |
|---|---|---|
| `rounds` | `int` | Number of think-act-observe cycles completed |
| `tool_calls_made` | `int` | Total individual tool invocations |
| `truncated_responses` | `int` | LLM responses where `finish_reason` indicated truncation |
| `truncated_observations` | `int` | Tool results truncated due to `max_observation_chars` |
| `messages_trimmed` | `int` | Number of rounds where message history was trimmed |

**Raises:**

- `MaxIterationsError` — when `max_rounds` is exhausted without a final answer; includes `cost` and `metadata` on the exception
- `BudgetExhaustedError` — when `max_cost` is exceeded before a call
- `TypeError` — if `provider` does not satisfy `ToolCallingProvider` (i.e., lacks `supports_tools = True`)
- `RateLimitError`, `PermanentError`, `ProviderError` — from the underlying provider

**Tool error handling:**

Unknown tool names and tool execution errors do not raise exceptions from `react_loop`. Instead, an error string is returned as the tool observation and the loop continues, giving the LLM an opportunity to recover.

**Example:**

```python
from executionkit import Provider, react_loop
from executionkit.types import Tool

async def search(query: str) -> str:
    return f"Results for: {query}"

search_tool = Tool(
    name="search",
    description="Search for information.",
    parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    execute=search,
)

result = await react_loop(provider, "What is the capital of Japan?", tools=[search_tool])
print(result.value)
print(f"Rounds: {result.metadata['rounds']}, calls: {result.metadata['tool_calls_made']}")
```

---

### `react_loop_sync()`

```python
def react_loop_sync(
    provider: ToolCallingProvider,
    prompt: str,
    tools: Sequence[Tool] = (),
    **kwargs: Any,
) -> PatternResult[str]
```

Synchronous wrapper for `react_loop()`. Accepts all the same keyword arguments.

Raises `RuntimeError` if called from within an already-running event loop.

---

## Composition

### `pipe()`

```python
async def pipe(
    provider: LLMProvider,
    prompt: str,
    *steps: PatternStep,
    max_budget: TokenUsage | None = None,
    **shared_kwargs: Any,
) -> PatternResult[Any]
```

Chains reasoning patterns in sequence. Each step's `value` is converted to a string and passed as the `prompt` to the next step. Costs are accumulated across all steps.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider` | `LLMProvider` | required | LLM provider passed unchanged to every step |
| `prompt` | `str` | required | Initial input prompt |
| `*steps` | `PatternStep` | required | Async pattern callables to chain in order |
| `max_budget` | `TokenUsage \| None` | `None` | Optional shared token/call budget across all steps; remaining budget is forwarded as `max_cost` to each step |
| `**shared_kwargs` | `Any` | — | Extra keyword arguments forwarded to every step that accepts them |

**Returns:** `PatternResult[Any]`

The result from the final step, with `cost` replaced by the cumulative cost across all steps. If `steps` is empty, returns the prompt as-is with zero cost.

**Metadata keys** (in addition to keys from the final step):

| Key | Type | Description |
|---|---|---|
| `step_count` | `int` | Number of steps executed |
| `step_metadata` | `list[dict]` | Metadata dict from each step, in order |

**Raises:**

- Any exception raised by a step, with `exc.cost` updated to include costs accumulated prior to the failure
- `BudgetExhaustedError` — when `max_budget` is exhausted within a step

**Keyword argument filtering:**

`pipe()` inspects each step's signature and forwards only the keyword arguments that the step explicitly accepts (unless the step declares `**kwargs`, in which case all shared kwargs are forwarded). This prevents `TypeError` when chaining patterns with different parameter sets.

**Example:**

```python
from executionkit import Provider, pipe, refine_loop, consensus

result = await pipe(
    provider,
    "Explain neural networks.",
    refine_loop,
    consensus,
    max_budget=TokenUsage(input_tokens=50000, output_tokens=20000, llm_calls=20),
)
print(result.value)
print(f"Steps: {result.metadata['step_count']}")
```

---

### `pipe_sync()`

```python
def pipe_sync(
    provider: LLMProvider,
    prompt: str,
    *steps: Any,
    **kwargs: Any,
) -> PatternResult[Any]
```

Synchronous wrapper for `pipe()`. Accepts all the same keyword arguments.

Raises `RuntimeError` if called from within an already-running event loop.

---

### `PatternStep`

```python
class PatternStep(Protocol):
    def __call__(
        self,
        provider: LLMProvider,
        prompt: str,
        **kwargs: Any,
    ) -> Awaitable[PatternResult[Any]]: ...
```

Callable protocol for a single step in a `pipe()` chain. The built-in pattern functions (`consensus`, `refine_loop`) satisfy this protocol. Custom steps must accept `provider` and `prompt` as positional-or-keyword parameters.

---

### `Kit`

```python
class Kit:
    def __init__(self, provider: LLMProvider, *, track_cost: bool = True) -> None
```

Session wrapper that holds a provider and optionally accumulates cumulative token usage across all pattern calls.

**Constructor parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider` | `LLMProvider` | required | The LLM provider to use for all calls |
| `track_cost` | `bool` | `True` | When `True`, accumulate usage across calls. Set to `False` to disable (e.g., in hot paths or tests) |

**Attributes:**

| Attribute | Type | Description |
|---|---|---|
| `provider` | `LLMProvider` | The provider passed at construction |
| `usage` | `TokenUsage` (property) | Cumulative token usage across all calls made through this Kit |

**Methods:**

#### `Kit.consensus()`

```python
async def consensus(self, prompt: str, **kwargs: Any) -> PatternResult[str]
```

Calls `consensus(self.provider, prompt, **kwargs)` and records the cost. All keyword arguments are forwarded to `consensus()`.

#### `Kit.refine()`

```python
async def refine(self, prompt: str, **kwargs: Any) -> PatternResult[str]
```

Calls `refine_loop(self.provider, prompt, **kwargs)` and records the cost. All keyword arguments are forwarded to `refine_loop()`.

#### `Kit.react()`

```python
async def react(self, prompt: str, tools: Sequence[Tool], **kwargs: Any) -> PatternResult[str]
```

Calls `react_loop(self.provider, prompt, tools, **kwargs)` and records the cost. The provider must satisfy `ToolCallingProvider`; `react_loop` raises `TypeError` if it does not.

#### `Kit.pipe()`

```python
async def pipe(self, prompt: str, *steps: Callable[..., Any], **kwargs: Any) -> PatternResult[Any]
```

Calls `pipe(self.provider, prompt, *steps, **kwargs)` and records the cost.

**Example:**

```python
from executionkit import Kit, Provider

provider = Provider(base_url="https://api.openai.com/v1", api_key="sk-...", model="gpt-4o-mini")
kit = Kit(provider)

result = await kit.consensus("What is 2+2?", num_samples=3)
print(result.value)
print(f"Total usage: {kit.usage}")
```

---

## Types

### `PatternResult[T]`

```python
@dataclass(frozen=True, slots=True)
class PatternResult(Generic[T]):
    value: T
    score: float | None = None
    cost: TokenUsage = field(default_factory=TokenUsage)
    metadata: MappingProxyType[str, Any] = field(default_factory=lambda: MappingProxyType({}))
```

Immutable return type for every reasoning pattern. `T` is typically `str`.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `value` | `T` | The pattern output (e.g., the winning response string) |
| `score` | `float \| None` | Quality score in [0.0, 1.0] if the pattern produces one; `None` otherwise |
| `cost` | `TokenUsage` | Token and call counts accumulated by this pattern run |
| `metadata` | `MappingProxyType[str, Any]` | Read-only mapping of pattern-specific data. Keys vary by pattern; see each pattern's documentation |

`metadata` is a `MappingProxyType` (immutable view). Do not rely on undocumented keys — they are considered private.

`str(result)` returns `str(result.value)`.

---

### `TokenUsage`

```python
@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
```

Immutable accumulator for token and call counts. Supports addition via `+`.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `input_tokens` | `int` | Total prompt tokens consumed |
| `output_tokens` | `int` | Total completion tokens generated |
| `llm_calls` | `int` | Total number of LLM API calls made |

**Operations:**

```python
usage_a + usage_b  # returns a new TokenUsage summing all three fields
```

---

### `Tool`

```python
@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Awaitable[str]]
    timeout: float = 30.0
```

Describes a tool available for LLM tool-calling (used with `react_loop`).

**Fields:**

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Tool name as registered with the LLM |
| `description` | `str` | Human/LLM-readable description of what the tool does |
| `parameters` | `dict[str, Any]` | JSON Schema object describing the function arguments |
| `execute` | `Callable[..., Awaitable[str]]` | Async callable invoked when the LLM requests this tool; receives keyword arguments matching `parameters`; must return a string |
| `timeout` | `float` | Per-call timeout in seconds (default: 30.0); overridden by `react_loop`'s `tool_timeout` if set |

**Methods:**

```python
def to_schema(self) -> dict[str, Any]
```

Returns the OpenAI-compatible function tool schema dict (used internally by `react_loop`).

**Example:**

```python
async def get_price(ticker: str) -> str:
    return f"${ticker}: 150.00"

price_tool = Tool(
    name="get_price",
    description="Get the current stock price for a ticker symbol.",
    parameters={
        "type": "object",
        "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. 'AAPL'"}},
        "required": ["ticker"],
    },
    execute=get_price,
    timeout=10.0,
)
```

---

### `VotingStrategy`

```python
class VotingStrategy(StrEnum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"
```

Strategy for `consensus()` voting.

| Value | Behavior |
|---|---|
| `MAJORITY` | The most common response wins. Ties are broken by the first occurrence in the sample order |
| `UNANIMOUS` | All responses must be identical (after whitespace normalization); raises `ConsensusFailedError` otherwise |

Accepts plain strings: `strategy="majority"` and `strategy=VotingStrategy.MAJORITY` are equivalent.

---

### `Evaluator`

```python
Evaluator = Callable[[str, LLMProvider], Awaitable[float]]
```

Type alias for the `evaluator` parameter of `refine_loop()`. An async callable that receives the current response text and the LLM provider, and returns a quality score in [0.0, 1.0].

---

## Provider

### `Provider`

```python
@dataclass(frozen=True, slots=True)
class Provider:
    base_url: str
    model: str
    api_key: str = ""
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    timeout: float = 120.0
```

Universal LLM provider. Posts JSON to `{base_url}/chat/completions` and parses the JSON response. Compatible with any OpenAI-compatible endpoint: OpenAI, Azure OpenAI, Ollama, Together AI, Groq, GitHub Models, and others.

**Constructor parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `base_url` | `str` | required | Base URL of the API endpoint (trailing slash optional) |
| `model` | `str` | required | Model identifier to pass in every request |
| `api_key` | `str` | `""` | API key sent as `Authorization: Bearer <key>`. Empty string omits the header |
| `default_temperature` | `float` | `0.7` | Default sampling temperature used when not overridden per-call |
| `default_max_tokens` | `int` | `4096` | Default max tokens used when not overridden per-call |
| `timeout` | `float` | `120.0` | HTTP request timeout in seconds |

`supports_tools` is always `True`, satisfying `ToolCallingProvider`.

**HTTP backend:**

`Provider` automatically uses `httpx.AsyncClient` (with connection pooling) when `httpx` is installed, and falls back to `asyncio.to_thread(urllib.request)` otherwise. Install the optional backend with:

```
pip install executionkit[httpx]
```

**Methods:**

#### `Provider.complete()`

```python
async def complete(
    self,
    messages: Sequence[dict[str, Any]],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: Sequence[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> LLMResponse
```

POST to `{base_url}/chat/completions` and return the parsed response.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `messages` | `Sequence[dict]` | required | OpenAI-format chat messages |
| `temperature` | `float \| None` | `None` | Overrides `default_temperature` when set |
| `max_tokens` | `int \| None` | `None` | Overrides `default_max_tokens` when set |
| `tools` | `Sequence[dict] \| None` | `None` | OpenAI-format tool schemas |
| `**kwargs` | `Any` | — | Additional fields merged into the request payload |

Raises `RateLimitError` (HTTP 429), `PermanentError` (HTTP 401/403/404), or `ProviderError` (other HTTP errors).

#### `Provider.aclose()`

```python
async def aclose(self) -> None
```

Release the underlying HTTP client. Call when the provider is no longer needed.

#### Context manager

`Provider` supports the async context manager protocol:

```python
async with Provider(base_url=..., model=...) as provider:
    result = await consensus(provider, "Hello")
```

**Example:**

```python
import os
from executionkit import Provider

# OpenAI
provider = Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o-mini",
)

# Ollama (local, no API key)
provider = Provider(
    base_url="http://localhost:11434/v1",
    model="llama3.2",
)
```

---

### `LLMProvider` Protocol

```python
@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...
```

Structural protocol for any LLM backend (PEP 544). Any class with a matching `complete` signature satisfies this protocol without explicit inheritance. Used by `consensus()`, `refine_loop()`, and `pipe()`.

`isinstance(obj, LLMProvider)` works at runtime.

---

### `ToolCallingProvider` Protocol

```python
@runtime_checkable
class ToolCallingProvider(LLMProvider, Protocol):
    supports_tools: Literal[True]
```

Extension of `LLMProvider` for providers that support tool calling. Required by `react_loop()`. The built-in `Provider` satisfies this protocol; `MockProvider` also satisfies it.

Custom providers must declare `supports_tools: Literal[True] = True` to satisfy this protocol.

---

### `LLMResponse`

```python
@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None
```

Parsed LLM completion response. Handles both OpenAI (`prompt_tokens`/`completion_tokens`) and Anthropic (`input_tokens`/`output_tokens`) usage key formats.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `content` | `str` | Text content of the response |
| `tool_calls` | `list[ToolCall]` | Tool call requests from the LLM (empty list if none) |
| `finish_reason` | `str` | Stop reason from the API (e.g., `"stop"`, `"length"`, `"tool_calls"`) |
| `usage` | `dict[str, Any]` | Raw usage dict from the API response |
| `raw` | `Any` | Full raw API response payload |

**Properties:**

| Property | Type | Description |
|---|---|---|
| `input_tokens` | `int` | Prompt tokens; normalizes OpenAI and Anthropic key names |
| `output_tokens` | `int` | Completion tokens; normalizes OpenAI and Anthropic key names |
| `total_tokens` | `int` | `input_tokens + output_tokens` |
| `has_tool_calls` | `bool` | `True` if `tool_calls` is non-empty |
| `was_truncated` | `bool` | `True` if `finish_reason` is `"length"` or `"max_tokens"` |

---

### `ToolCall`

```python
@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
```

A single tool invocation extracted from an LLM response.

**Fields:**

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Tool call identifier from the API (used in tool-role reply messages) |
| `name` | `str` | Name of the tool to invoke |
| `arguments` | `dict[str, Any]` | Parsed JSON arguments for the tool call |

---

## Support Utilities

### `MockProvider`

```python
@dataclass
class MockProvider:
    responses: list[str | LLMResponse] = field(default_factory=list)
    exception: Exception | None = None
```

Test double implementing both `LLMProvider` and `ToolCallingProvider`. Returns pre-configured responses in order, cycling when exhausted. Optionally raises a configured exception to test error paths.

**Constructor parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `responses` | `list[str \| LLMResponse]` | `[]` | Responses to return in order. Strings are wrapped in `LLMResponse`. Cycles when exhausted |
| `exception` | `Exception \| None` | `None` | When set, every `complete()` call raises this exception |

**Attributes/properties:**

| Name | Type | Description |
|---|---|---|
| `calls` | `list[_CallRecord]` | All recorded call arguments, in order |
| `call_count` | `int` (property) | Number of calls made so far |
| `last_call` | `_CallRecord \| None` (property) | Most recent call record, or `None` |
| `supports_tools` | `Literal[True]` | Always `True` |

**Example:**

```python
from executionkit import MockProvider, consensus

mock = MockProvider(responses=["Paris", "Paris", "London"])
result = await consensus(mock, "Capital of France?", num_samples=3)
assert result.value == "Paris"
assert mock.call_count == 3
```

---

### `RetryConfig`

```python
@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable: tuple[type[Exception], ...] = (RateLimitError, ProviderError)
```

Immutable retry configuration with exponential backoff and full jitter. Pass to any pattern via the `retry` parameter.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `max_retries` | `int` | `3` | Maximum retry attempts. `0` disables retries |
| `base_delay` | `float` | `1.0` | Base delay in seconds before the first retry |
| `max_delay` | `float` | `60.0` | Maximum delay cap in seconds |
| `exponential_base` | `float` | `2.0` | Multiplier for exponential backoff |
| `retryable` | `tuple[type[Exception], ...]` | `(RateLimitError, ProviderError)` | Exception types that trigger retries |

**Methods:**

- `should_retry(exc: Exception) -> bool` — returns `True` if `exc` is an instance of any retryable type
- `get_delay(attempt: int) -> float` — returns a jittered backoff delay for the given attempt (1-indexed); uses full jitter to prevent thundering-herd effects

### `DEFAULT_RETRY`

```python
DEFAULT_RETRY: RetryConfig = RetryConfig()
```

The default `RetryConfig` instance used by all patterns when `retry=None`. 3 retries, 1s base delay, 60s max, exponential base 2, retries on `RateLimitError` and `ProviderError`.

---

### `ConvergenceDetector`

```python
@dataclass
class ConvergenceDetector:
    delta_threshold: float = 0.01
    patience: int = 3
    score_threshold: float | None = None
```

Tracks score history and detects convergence. Used internally by `refine_loop()`. Declare convergence when:
- `score_threshold` is set and the current score meets or exceeds it, OR
- The score delta has been below `delta_threshold` for `patience` consecutive iterations.

**Fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `delta_threshold` | `float` | `0.01` | Minimum meaningful score improvement |
| `patience` | `int` | `3` | Consecutive stale iterations before stopping |
| `score_threshold` | `float \| None` | `None` | Optional absolute score target for early exit |

**Methods:**

- `should_stop(score: float) -> bool` — record a score and return whether convergence is reached; raises `ValueError` if score is NaN or outside [0.0, 1.0]
- `reset() -> None` — clear all tracked state

---

### `CostTracker`

```python
class CostTracker:
    def __init__(self) -> None
```

Mutable accumulator for token and call counts. Used internally by all patterns. Exposed publicly for custom pattern implementations.

**Methods:**

| Method | Description |
|---|---|
| `record(response: LLMResponse) -> None` | Record usage from a single LLM response (increments call count) |
| `add_usage(usage: TokenUsage) -> None` | Add pre-computed usage (e.g., from a pattern result) |
| `to_usage() -> TokenUsage` | Return an immutable snapshot of accumulated usage |

**Properties:**

| Property | Type | Description |
|---|---|---|
| `call_count` | `int` | Number of LLM calls recorded so far |
| `total_tokens` | `int` | Total input + output tokens |

---

### `extract_json()`

```python
def extract_json(text: str) -> dict[str, Any] | list[Any]
```

Extract JSON from LLM output using multiple strategies, in order:
1. `json.loads(text.strip())`
2. Strip markdown fences (` ```json ... ``` ` or generic code fences)
3. Balanced-brace extraction — find the first `{` or `[` and track nesting depth respecting string boundaries

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `text` | `str` | Raw LLM response text that may contain JSON |

**Returns:** `dict[str, Any] | list[Any]` — parsed JSON object or array

**Raises:** `ValueError` — if no valid JSON can be extracted

---

### `checked_complete()`

```python
async def checked_complete(
    provider: LLMProvider,
    messages: Sequence[dict[str, Any]],
    tracker: CostTracker,
    budget: TokenUsage | None,
    retry: RetryConfig | None,
    **kwargs: Any,
) -> LLMResponse
```

Low-level utility: performs a budget check, then calls `provider.complete()` wrapped in `with_retry()`, and records usage. Used by all built-in patterns. Useful for building custom patterns.

**Raises:** `BudgetExhaustedError` if the budget is exceeded before the call.

---

### `validate_score()`

```python
def validate_score(score: float) -> float
```

Validate that an evaluator score is in [0.0, 1.0] and not NaN.

**Returns:** The validated score unchanged.

**Raises:** `ValueError` if the score is NaN or outside [0.0, 1.0].

---

## Error Hierarchy

All exceptions carry `cost: TokenUsage` and `metadata: dict[str, Any]` attributes set at raise time.

```
ExecutionKitError
├── LLMError                    — provider communication errors
│   ├── RateLimitError          — HTTP 429; has retry_after: float
│   ├── PermanentError          — HTTP 401/403/404; non-retryable
│   └── ProviderError           — other HTTP errors; retryable
└── PatternError                — pattern logic errors
    ├── BudgetExhaustedError    — token or call budget exceeded
    ├── ConsensusFailedError    — unanimous strategy failed
    └── MaxIterationsError      — loop hit max_rounds/max_iterations
```

### `ExecutionKitError`

```python
class ExecutionKitError(Exception):
    def __init__(self, message: str, *, cost: TokenUsage | None = None, metadata: dict[str, Any] | None = None) -> None
```

Base class for all ExecutionKit exceptions.

| Attribute | Type | Description |
|---|---|---|
| `cost` | `TokenUsage` | Token usage accumulated before the error |
| `metadata` | `dict[str, Any]` | Pattern-specific context at the point of failure |

### `LLMError`

Raised for errors originating from LLM provider communication. Inherits from `ExecutionKitError`.

### `RateLimitError`

```python
class RateLimitError(LLMError):
    retry_after: float  # seconds to wait before retrying
```

Raised when the provider returns HTTP 429. `retry_after` is parsed from the `Retry-After` response header (defaults to `1.0` seconds).

### `PermanentError`

Raised for non-retryable provider errors: HTTP 401 (authentication), 403 (forbidden), or 404 (not found). Inherits from `LLMError`.

### `ProviderError`

Catch-all retryable provider error for unexpected HTTP failures not covered by `RateLimitError` or `PermanentError`. Inherits from `LLMError`.

### `PatternError`

Raised by reasoning pattern logic (not provider communication). Inherits from `ExecutionKitError`.

### `BudgetExhaustedError`

Raised when a `TokenUsage` budget passed as `max_cost` is exceeded before an LLM call is dispatched. `metadata` includes a `"budget"` key with the configured `TokenUsage` limit. Inherits from `PatternError`.

### `ConsensusFailedError`

Raised by `consensus()` when `strategy="unanimous"` and the samples do not all produce identical responses (after whitespace normalization). Inherits from `PatternError`.

### `MaxIterationsError`

Raised by `react_loop()` when `max_rounds` is exhausted without the LLM producing a final answer (response without tool calls). `cost` and `metadata` reflect the state at the point of failure. Inherits from `PatternError`.

---

## Installation

### Minimal (stdlib HTTP only)

```
pip install executionkit
```

Uses `asyncio.to_thread(urllib.request)` for HTTP. No additional dependencies.

### With httpx backend (recommended)

```
pip install executionkit[httpx]
```

Enables `httpx.AsyncClient` with connection pooling and keep-alive. Improves throughput for patterns that make many concurrent calls (e.g., `consensus()` with high `num_samples`).

### Requirements

- Python 3.11 or later
- No mandatory runtime dependencies
- Optional: `httpx>=0.27`
