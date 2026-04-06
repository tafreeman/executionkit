# ExecutionKit

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Coverage: 83%](https://img.shields.io/badge/coverage-83%25-brightgreen)](pyproject.toml)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen)](https://github.com/your-org/executionkit/actions)

Composable LLM reasoning patterns with budget-aware execution.

ExecutionKit fills the gap between raw chat calls and full orchestration stacks — more
power than one-off prompts, less weight than a framework.

## Quick Example

```python
import os
from executionkit import consensus, Provider

provider = Provider("https://api.openai.com/v1", api_key=os.environ["OPENAI_API_KEY"], model="gpt-4o-mini")

result = await consensus(provider, "Classify this support ticket: ...", num_samples=5)
print(result)                                # The classification
print(result.cost)                           # TokenUsage(input_tokens=250, output_tokens=45, llm_calls=5)
print(result.metadata["agreement_ratio"])    # 0.8 = 4 of 5 agreed
```

Works with ANY OpenAI-compatible endpoint — zero config change:

```python
ollama   = Provider("http://localhost:11434/v1", model="llama3.2")
github   = Provider("https://models.inference.ai.azure.com", api_key=GITHUB_TOKEN, model="gpt-4o-mini")
together = Provider("https://api.together.xyz/v1", api_key=TOGETHER_KEY, model="meta-llama/Llama-3-70b")
groq     = Provider("https://api.groq.com/openai/v1", api_key=GROQ_KEY, model="llama-3.3-70b")
```

## Features

- Composable reasoning patterns: consensus, refine_loop, react_loop
- Budget-aware execution with per-call cost tracking
- Works with any OpenAI-compatible endpoint — zero config change
- Zero runtime dependencies (stdlib only; httpx optional for connection pooling)
- Type-safe with full `mypy --strict` support
- Prompt injection defense in default evaluator (XML delimiter sandboxing)
- API key masked in `Provider.__repr__`; credentials redacted from error messages

## Installation

```bash
pip install executionkit
```

For high-throughput workloads requiring connection pooling:

```bash
pip install executionkit[httpx]
```

The `[httpx]` extra adds `httpx` as the HTTP backend. Without it, the stdlib
`urllib` backend is used (one new TCP connection per call).

Requires Python 3.11+.

## Quick Start

### Provider setup

```python
import os
from executionkit import Provider

provider = Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o-mini",
)
```

### Consensus

```python
from executionkit import consensus

result = await consensus(provider, "What is the capital of France?", num_samples=3)
print(result)                                     # Paris
print(result.metadata["agreement_ratio"])         # 1.0
print(result.cost)                                # TokenUsage(...)
```

### Refine loop

```python
from executionkit import refine_loop

result = await refine_loop(
    provider,
    "Write a one-paragraph summary of the Turing test.",
    target_score=0.85,
    max_iterations=4,
)
print(result)                                     # Best response found
print(result.score)                               # 0.91
print(result.metadata["iterations"])              # 2
```

### React loop (tool calling)

```python
from executionkit import react_loop, Tool

async def _calculator(expression: str) -> str:
    # Use a safe AST-based evaluator — never eval() untrusted input
    ...

calc_tool = Tool(
    name="calculator",
    description="Evaluate a math expression and return the result.",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
    execute=_calculator,
)

result = await react_loop(provider, "What is 17 * 83?", tools=[calc_tool])
print(result)                                     # 1411
print(result.metadata["tool_calls_made"])         # 1
```

> **Security note:** Never use Python's `eval()` with untrusted LLM output. The
> example above uses a safe AST-based evaluator. See `examples/react_tool_use.py`
> for the full implementation.

## Provider Setup

`Provider` speaks the OpenAI-compatible `/chat/completions` format. By default
it uses stdlib `urllib` with no external dependencies. When `httpx` is
installed (via `pip install executionkit[httpx]`), it automatically switches to
an `httpx.AsyncClient` with connection pooling.

`Provider` supports the async context manager protocol for clean resource
management:

```python
async with Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o-mini",
) as provider:
    result = await consensus(provider, "...")
```

Calling `await provider.aclose()` manually is equivalent when a context manager
is not used.

```python
# OpenAI
provider = Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o-mini",
)

# Ollama (local — no API key needed)
provider = Provider(
    base_url="http://localhost:11434/v1",
    model="llama3.2",
)

# GitHub Models
provider = Provider(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],
    model="gpt-4o-mini",
)

# Together AI
provider = Provider(
    base_url="https://api.together.xyz/v1",
    api_key=os.environ["TOGETHER_API_KEY"],
    model="meta-llama/Llama-3-70b",
)

# Groq
provider = Provider(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
    model="llama-3.3-70b",
)
```

Optional `Provider` parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `default_temperature` | `0.7` | Sampling temperature used when not overridden per call |
| `default_max_tokens` | `4096` | Max tokens when not overridden per call |
| `timeout` | `120.0` | HTTP request timeout in seconds |

`Provider.__repr__` masks the API key as `***` to prevent accidental credential
leakage in logs and debug output.

## Patterns Reference

### `consensus(provider, prompt, *, ...)`

Run `num_samples` completions in parallel and aggregate via voting.
Whitespace and trailing newlines are normalized before comparison, so
two responses that differ only in whitespace are counted as identical.

```python
async def consensus(
    provider: LLMProvider,
    prompt: str,
    *,
    num_samples: int = 5,
    strategy: VotingStrategy | str = "majority",  # or "unanimous"
    temperature: float = 0.9,
    max_tokens: int = 4096,
    max_concurrency: int = 5,
    retry: RetryConfig | None = None,
) -> PatternResult[str]: ...
```

Metadata keys: `agreement_ratio`, `unique_responses`, `tie_count`.

Raises `ConsensusFailedError` when `strategy="unanimous"` and not all
responses are identical.

### `refine_loop(provider, prompt, *, ...)`

Iteratively improve a response until a score target or convergence.
The default evaluator wraps the text in XML delimiters to prevent
adversarial content inside the response from overriding the scoring
instruction. Supply a custom `evaluator=` for production use.

`_parse_score` validates the 0-10 range and raises `ValueError` if
the evaluator returns a score outside that range.

```python
async def refine_loop(
    provider: LLMProvider,
    prompt: str,
    *,
    evaluator: Evaluator | None = None,   # async (text, provider) -> float[0,1]
    target_score: float = 0.9,
    max_iterations: int = 5,
    patience: int = 3,
    delta_threshold: float = 0.01,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[str]: ...
```

Metadata keys: `iterations`, `converged`, `score_history`.

### `react_loop(provider, prompt, tools, *, ...)`

Think-act-observe loop with tool calling. Tool call arguments are
validated against the tool's JSON Schema before execution (stdlib only,
no `jsonschema` dependency required).

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
) -> PatternResult[str]: ...
```

`max_history_messages` caps the message history sent to the LLM on each
round. When set, the first message (original prompt) is always preserved,
and only the most recent `max_history_messages - 1` messages are kept.
This bounds memory growth for long-running loops. `None` (default)
disables trimming.

Metadata keys: `rounds`, `tool_calls_made`, `truncated_responses`,
`truncated_observations`, `messages_trimmed`.

Raises `MaxIterationsError` when `max_rounds` is exhausted without a
final answer.

## Composition

`pipe()` chains patterns, threading each result's value as the next prompt.
Costs accumulate; an optional shared budget is passed to every step.

```python
from executionkit import pipe, consensus, refine_loop
from functools import partial

result = await pipe(
    provider,
    "Explain gradient descent in simple terms.",
    consensus,
    partial(refine_loop, target_score=0.9),
)

print(result)          # Final refined value
print(result.cost)     # Cumulative cost across both steps
```

## Kit Session

`Kit` tracks cumulative usage across multiple pattern calls in a session.

```python
from executionkit import Kit

kit = Kit(provider)

r1 = await kit.consensus("Classify: ...", num_samples=3)
r2 = await kit.refine("Summarise: ...")

print(kit.usage)   # TokenUsage across all calls
```

## Custom Providers

Any object with a matching `complete` method satisfies the `LLMProvider`
protocol via structural subtyping — no inheritance required:

```python
from executionkit.provider import LLMResponse

class MyProvider:
    async def complete(
        self,
        messages,
        *,
        temperature=None,
        max_tokens=None,
        tools=None,
        **kwargs,
    ) -> LLMResponse:
        # call your API here
        return LLMResponse(content="Hello", usage={})
```

Pass any conforming provider to `Kit`, `consensus`, `refine_loop`, or
`react_loop`. The built-in `Provider` class is one implementation; you can
swap in any other without changing pattern code.

## Synchronous Usage

All patterns are async. Synchronous convenience wrappers are provided for
use outside of async contexts (raises `RuntimeError` inside a running event
loop — use `await` instead):

```python
from executionkit import Provider, consensus_sync, refine_loop_sync, react_loop_sync, pipe_sync

provider = Provider(base_url="https://api.openai.com/v1", model="gpt-4o", api_key="...")

result = consensus_sync(provider, "What is 2+2?")
print(result.value)
```

Using `asyncio.run()` directly is also fine:

```python
import asyncio
from executionkit import Provider, consensus

result = asyncio.run(consensus(provider, "What is 2+2?"))
```

## Error Hierarchy

All exceptions inherit from `ExecutionKitError` and carry `.cost` (accumulated
`TokenUsage`) and `.metadata` fields.

| Exception | Cause |
|-----------|-------|
| `LLMError` | Base for provider communication errors |
| `RateLimitError` | HTTP 429 — retryable; carries `retry_after` |
| `PermanentError` | HTTP 401/403/404 — not retryable |
| `ProviderError` | Unexpected HTTP failure — retryable |
| `PatternError` | Base for pattern logic errors |
| `BudgetExhaustedError` | Token or call budget exceeded |
| `ConsensusFailedError` | Unanimous strategy could not agree |
| `MaxIterationsError` | Loop hit `max_rounds` / `max_iterations` |

Error messages containing credential-like substrings (patterns matching
`sk...`, `key...`, `token...`, `secret...`, `bearer...`, `auth...`) are
automatically redacted to `[REDACTED]`.

## Security

**Prompt injection defense.** The default `refine_loop` evaluator wraps the
text being scored in `<response_to_rate>` XML delimiters and instructs the
LLM to ignore any instructions inside them. This mitigates prompt injection
attacks where adversarial content in a generated response attempts to
override the scoring instruction.

**API key masking.** `Provider.__repr__` always shows `api_key='***'`
regardless of the actual key length or prefix. Keys are never written to
repr output, log lines, or exception messages.

**Credential redaction in errors.** HTTP error messages returned by
providers are scanned for credential-shaped substrings before being
included in exception messages. Matching patterns are replaced with
`[REDACTED]`.

**SAST scanning.** Bandit is run in CI on every commit. Configuration is
in `pyproject.toml` under `[tool.bandit]`.

**Tool argument validation.** `react_loop` validates tool call arguments
against each tool's JSON Schema (`required` fields, `additionalProperties`,
and primitive type checks) before invoking the tool execute function.

## Known Limitations

**No connection pooling (stdlib backend).**
The default HTTP backend opens a new TCP+TLS connection per LLM call. For
high-throughput workloads (e.g. `consensus` with many samples or long
`react_loop` chains), install `executionkit[httpx]` to enable the `httpx`
connection-pool backend.

**`react_loop` context growth.**
The message history grows with every tool call round. For loops exceeding ~20
rounds or with large tool outputs per round, set `max_history_messages` to
avoid hitting the model's context window limit. The parameter preserves the
original prompt and keeps only the most recent messages.

**Default evaluator in `refine_loop`.**
The built-in quality scorer is a lightweight LLM prompt intended for
development use. Supply a custom `evaluator=` function for production
workloads or when input may contain adversarial content.

**No streaming support.**
All completions are batch requests. Streaming responses are not currently
supported.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code style, and PR process.

The test suite has 300 tests at 83% coverage (enforced at 80% by CI).
Run tests with:

```bash
pytest
```

## License

MIT. See [LICENSE](LICENSE).
