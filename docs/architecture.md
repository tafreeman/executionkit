# ExecutionKit Architecture

## Design Principles

ExecutionKit is a minimal library for composable LLM reasoning. Five principles
shape every design decision:

1. **Zero runtime dependencies.** `dependencies = []` in `pyproject.toml`. The
   optional `httpx` extra is additive — the stdlib `urllib` backend is always
   present. Consumers can import ExecutionKit anywhere without dependency
   conflicts.

2. **Flat package layout.** All importable names live under `executionkit/`
   directly (no `src/` wrapper). Sub-packages (`patterns/`, `engine/`) exist
   only for organisational grouping, not namespace isolation.

3. **Frozen value types.** Every object that crosses a function boundary is
   `@dataclass(frozen=True, slots=True)`. Patterns never return mutable state;
   callers receive a `PatternResult` that cannot be altered after the fact. This
   prevents hidden side-effects and makes results safe to cache, share, and
   compare.

4. **Async-first, sync wrappers provided.** All pattern functions are `async`.
   Synchronous convenience wrappers (`consensus_sync`, `refine_loop_sync`,
   `react_loop_sync`, `pipe_sync`) live in `__init__.py` and call
   `asyncio.run()`, raising a helpful error when called inside a running loop.

5. **Composable, not opinionated.** Patterns are standalone async functions that
   accept any `LLMProvider`-conforming object. `pipe()` chains them without
   coupling. The `Kit` facade is optional sugar — nothing requires it.

---

## Module Map

```
executionkit/
├── __init__.py          — public API surface; sync wrappers
├── types.py             — frozen value types: PatternResult, TokenUsage, Tool, VotingStrategy, Evaluator
├── errors.py            — 9-class exception hierarchy (F-06: extracted from provider.py)
├── provider.py          — LLMProvider protocol, ToolCallingProvider protocol,
│                          Provider concrete class, LLMResponse, ToolCall;
│                          re-exports error classes from errors.py for backwards compatibility;
│                          _classify_http_error() is the single HTTP status→exception mapping
│                          point for both urllib and httpx backends (F-02)
├── cost.py              — CostTracker mutable accumulator
├── compose.py           — pipe() composition helper, PatternStep protocol
├── kit.py               — Kit session facade (provider + cumulative usage)
├── _mock.py             — MockProvider test double (satisfies both protocols)
├── patterns/
│   ├── base.py          — checked_complete(), validate_score(), _TrackedProvider;
│   │                      _check_budget() uses getattr() field loop replacing per-field
│   │                      if-chains (F-05/F-08); _TrackedProvider.supports_tools delegates
│   │                      to wrapped provider via getattr (F-04)
│   ├── consensus.py     — parallel majority/unanimous voting
│   ├── refine_loop.py   — iterative score-guided refinement
│   └── react_loop.py    — tool-calling think-act-observe loop
└── engine/
    ├── convergence.py   — ConvergenceDetector (delta + patience)
    ├── retry.py         — RetryConfig, with_retry() exponential backoff
    ├── parallel.py      — gather_strict() / gather_resilient() semaphore wrappers
    └── json_extraction.py — extract_json() multi-strategy JSON parser
```

### Dependency graph (arrows = "imports from")

```
__init__  ──► kit, compose, patterns/*, engine/*, provider, types, _mock
kit       ──► patterns/*, compose, provider, types, cost
compose   ──► provider, types
patterns/base    ──► cost, engine/retry, provider, types
patterns/consensus  ──► cost, engine/parallel, engine/retry, patterns/base, provider, types
patterns/refine_loop ──► cost, engine/convergence, engine/retry, patterns/base, provider, types
patterns/react_loop  ──► cost, engine/retry, patterns/base, provider, types
provider  ──► types, errors  (re-exports all 9 error classes from errors.py)
errors    ──► types
cost      ──► types
engine/*  ──► provider (retry only)
```

The dependency flows strictly downward. No engine module imports a pattern;
no types module imports provider details. This keeps the layering clean and
prevents circular imports.

---

## Data Flow

A typical call through the library follows this path:

```
User code
  │
  ▼
Kit.refine(prompt)          ← optional session facade
  │
  ▼
refine_loop(provider, prompt, ...)
  │
  ├─► CostTracker()          ← fresh mutable accumulator for this call
  ├─► ConvergenceDetector()  ← stateful score tracker
  │
  ▼
checked_complete(provider, messages, tracker, budget, retry)
  │  [patterns/base.py]
  ├─► budget guard            ← raises BudgetExhaustedError if over limit
  ├─► tracker._calls += 1    ← TOCTOU-safe pre-increment
  │
  ▼
with_retry(provider.complete, config, messages, **kwargs)
  │  [engine/retry.py]
  └─► provider.complete(messages, ...)
        │  [provider.py — Provider]
        ├─► _post() → httpx or urllib → HTTP POST to /chat/completions
        └─► _parse_response() → LLMResponse(content, tool_calls, usage, ...)
  │
  ▼  (on success)
tracker.record_without_call(response)   ← adds tokens, call slot already counted
  │
  ▼
Evaluator(text, provider)              ← optional; can re-enter checked_complete
  │
  ▼
ConvergenceDetector.should_stop(score) ← returns bool; loop continues or exits
  │
  ▼
PatternResult(value, score, cost=tracker.to_usage(), metadata=MappingProxyType(...))
  │
  ▼
Kit._record(result.cost)               ← adds to session cumulative tracker
  │
  ▼
User code receives PatternResult       ← immutable, complete
```

For `consensus`, the flow fans out: `gather_strict()` runs `num_samples`
`checked_complete()` coroutines concurrently behind a semaphore, collects
results, then applies the voting strategy before returning a single `PatternResult`.

For `react_loop`, the flow iterates: each round calls `checked_complete()`, then
dispatches any tool calls via `asyncio.wait_for(tool.execute(...))`, appends
tool-role messages, and loops until the LLM returns no tool calls or
`max_rounds` is hit.

---

## Immutability Contract

All value objects use `@dataclass(frozen=True, slots=True)`:

| Type | Where defined |
|------|---------------|
| `TokenUsage` | `types.py` |
| `PatternResult[T]` | `types.py` |
| `Tool` | `types.py` |
| `ToolCall` | `provider.py` |
| `LLMResponse` | `provider.py` |
| `Provider` | `provider.py` |
| `RetryConfig` | `engine/retry.py` |

`frozen=True` prevents field assignment after construction. `slots=True` saves
memory and makes attribute access faster — at the cost of forbidding `__dict__`.

`PatternResult.metadata` is additionally wrapped in `types.MappingProxyType` so
that even the mapping itself is read-only. Pattern internals build a plain
`dict[str, Any]` during execution, then wrap it only at the point of return.

The one intentional exception is `Provider.__post_init__`, which uses
`object.__setattr__` to set two derived private fields (`_client`, `_use_httpx`)
after construction. This is the standard Python pattern for computed state on
frozen dataclasses and does not violate the public immutability contract because
both fields are marked `repr=False, compare=False, hash=False`.

`CostTracker` is intentionally mutable — it is a private accumulator that only
exists within a single pattern invocation and is never exposed to user code
directly. Its snapshot is emitted as an immutable `TokenUsage` via `to_usage()`.

---

## Error Handling Architecture

The full 9-class exception hierarchy lives in `executionkit/errors.py` (F-06).
`provider.py` re-exports all nine classes under the same names so that existing
`from executionkit.provider import XError` imports continue to work without
modification (PEP 387 backwards compatibility).

```
ExecutionKitError              ← executionkit/errors.py
├── LLMError                  ← provider communication failures
│   ├── RateLimitError        ← HTTP 429; carries retry_after float
│   ├── PermanentError        ← HTTP 401/403/404; do not retry
│   └── ProviderError         ← catch-all retryable HTTP failures
└── PatternError              ← reasoning logic failures
    ├── BudgetExhaustedError  ← token or call budget exceeded
    ├── ConsensusFailedError  ← unanimous strategy failed
    └── MaxIterationsError    ← loop hit max_rounds/max_iterations
```

All errors carry `cost: TokenUsage` so callers can see what was spent before
the failure. `pipe()` augments errors with the cumulative cross-step cost before
re-raising.

**HTTP error classification:** `_classify_http_error()` in `provider.py` is the
single function responsible for mapping HTTP status codes to the correct error
subclass. Both the `_post_httpx` and `_post_urllib` backends call it, eliminating
duplicated mapping logic (F-02). This mirrors the pattern used by the Anthropic
SDK's `_make_status_error()`.

**Retry boundary:** `with_retry()` in `engine/retry.py` only retries
`RateLimitError` and `ProviderError`. `PermanentError` propagates immediately.
`asyncio.CancelledError` is always re-raised without retry.

**Pattern boundary:** patterns let `LLMError` propagate; they raise their own
`PatternError` subclass when their own invariants are violated (budget exceeded,
consensus impossible, iterations exhausted).

**Tool boundary:** `react_loop` catches all exceptions from tool execution and
returns them as error-string observations rather than propagating. This is
intentional: a broken tool should not abort a reasoning loop.

---

## Security Layers

### Credential redaction in error messages

`provider.py::_redact_sensitive()` uses a regex to replace substrings that
look like API keys (`sk-...`, `key-...`, `token-...`, etc.) with `[REDACTED]`
in all HTTP error messages before they surface in `PermanentError` or
`ProviderError`.

`Provider.__repr__` masks the `api_key` field entirely — it prints `'***'` if
non-empty, and `''` if empty. Never log provider instances at INFO level or
above in production.

### XML sandboxing in the default evaluator

`refine_loop`'s built-in evaluator wraps generated content in
`<response_to_rate>` XML delimiters and prepends an explicit instruction to
ignore any instructions inside those tags. This mitigates prompt injection
attacks where adversarial content in the LLM output could override the scoring
instruction. Content is also truncated to 32 768 characters before being
embedded.

### Tool argument validation

`react_loop` calls `_validate_tool_args()` against the tool's JSON Schema before
invoking the tool. Missing required fields and type mismatches are caught and
returned as error observations rather than passed to the tool. This prevents
malformed LLM output from causing unexpected behaviour in tool implementations.

### No eval or exec

ExecutionKit never calls `eval()` or `exec()` on LLM output. JSON is parsed
with `json.loads()` only.

### Bandit in CI

`bandit[toml]` is a dev dependency. `pyproject.toml` configures it with
targeted skips (`B101` assert guards, `B310` urllib intentional HTTP client,
`B311` jitter random). Any new code must pass Bandit without adding blanket
skips.

---

## Extension Points

### Implementing a custom LLMProvider

Any class with this method signature satisfies the `LLMProvider` structural
protocol (PEP 544 — no inheritance required):

```python
from executionkit import LLMProvider, LLMResponse

class MyProvider:
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        ...
```

To satisfy `ToolCallingProvider` (required by `react_loop`), additionally set:

```python
    supports_tools: Literal[True] = True
```

Use `MockProvider` from `executionkit._mock` in tests — it accepts a list of
string or `LLMResponse` responses and cycles through them.

### Implementing a custom pattern

A pattern is an async function with this signature:

```python
async def my_pattern(
    provider: LLMProvider,
    prompt: str,
    **kwargs: Any,
) -> PatternResult[str]:
    ...
```

Use `checked_complete()` from `patterns/base.py` instead of calling
`provider.complete()` directly. It handles budget enforcement, retry wrapping,
and call-slot TOCTOU safety in one call.

Return a `PatternResult` with a `MappingProxyType` metadata dict. Document all
public metadata keys in the function docstring under a `Metadata:` section.

To make the pattern composable with `pipe()`, ensure it accepts `max_cost` as a
keyword argument (forwarded by `pipe` for budget propagation) or declare
`**kwargs` to absorb it silently.

### Evaluator functions

An `Evaluator` is:

```python
Evaluator: TypeAlias = Callable[[str, LLMProvider], Awaitable[float]]
```

It receives the response text and the same provider. Return a float in
`[0.0, 1.0]`. Use `validate_score()` from `patterns/base.py` to ensure the
value is in range before returning.

---

## Engine Layer

### `engine/convergence.py` — ConvergenceDetector

Stateful detector used inside `refine_loop`. Call `should_stop(score)` after
each iteration. Returns `True` when either:
- `score >= score_threshold` (absolute target reached), or
- The score delta has been below `delta_threshold` for `patience` consecutive
  iterations.

`reset()` clears all state. The detector is not thread-safe — create one per
loop invocation.

### `engine/retry.py` — RetryConfig and with_retry

`RetryConfig` (frozen dataclass) holds `max_retries`, `base_delay`, `max_delay`,
`exponential_base`, and the tuple of retryable exception types. `DEFAULT_RETRY`
is the module-level singleton with sensible defaults (3 retries, 1 s base, 60 s
cap, factor 2).

`with_retry(fn, config, *args, **kwargs)` wraps any async callable. Uses full
jitter (`random.uniform(0, cap)`) to prevent thundering-herd effects when many
coroutines retry simultaneously. `CancelledError` is always re-raised
immediately.

### `engine/parallel.py` — gather_strict and gather_resilient

Both functions accept a list of coroutines and a `max_concurrency` semaphore
limit.

- `gather_strict` — all-or-nothing. Uses `asyncio.TaskGroup`. If exactly one
  task fails, the exception is unwrapped from the `ExceptionGroup` for cleaner
  tracebacks. Used by `consensus`.
- `gather_resilient` — tolerant. Uses `asyncio.gather(return_exceptions=True)`.
  Returns exceptions as values in the result list. Suitable for fan-out where
  partial results are acceptable.

### `engine/json_extraction.py` — extract_json

Three-strategy extractor for JSON embedded in LLM prose:

1. Raw `json.loads()` on stripped text.
2. Regex to strip ` ```json ``` ` or generic ` ``` ``` ` markdown fences.
3. Balanced-brace scan: finds the first `{` or `[`, tracks nesting depth while
   respecting string boundaries and escape sequences, extracts the substring
   ending at depth zero.

Returns `dict | list`. Raises `ValueError` if no valid JSON is found. Handles
both objects and arrays.
