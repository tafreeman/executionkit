# ExecutionKit

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
- Zero runtime dependencies (stdlib only)
- Type-safe with full `mypy --strict` support

## Installation

```bash
pip install executionkit
```

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
from examples.react_tool_use import _safe_eval

calc_tool = Tool(
    name="calculator",
    description="Evaluate a math expression and return the result.",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
    execute=lambda expression: str(_safe_eval(expression)),
)

result = await react_loop(provider, "What is 17 * 83?", tools=[calc_tool])
print(result)                                     # 1411
print(result.metadata["tool_calls_made"])         # 1
```

> ⚠️ **Security note:** Never use Python's `eval()` with untrusted LLM output. The example above uses a safe AST-based evaluator. See `examples/react_tool_use.py` for the full implementation.

## Provider Setup

`Provider` speaks the OpenAI-compatible `/chat/completions` format over stdlib
`urllib` — no SDK required.

```python
from executionkit import Provider

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

Optional Provider parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `default_temperature` | `0.7` | Sampling temperature used when not overridden |
| `default_max_tokens` | `4096` | Max tokens when not overridden per call |
| `timeout` | `120.0` | HTTP request timeout in seconds |

## Patterns Reference

### `consensus(provider, prompt, *, ...)`

Run `num_samples` completions in parallel and aggregate via voting.

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

### `refine_loop(provider, prompt, *, ...)`

Iteratively improve a response until a score target or convergence.

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

Think-act-observe loop with tool calling.

```python
async def react_loop(
    provider: LLMProvider,
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
) -> PatternResult[str]: ...
```

Metadata keys: `rounds`, `tool_calls_made`.

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

All patterns are async. To call them from synchronous code, use
`asyncio.run()`:

```python
import asyncio
from executionkit import Provider, Kit

provider = Provider(base_url="https://api.openai.com/v1", model="gpt-4o", api_key="...")
kit = Kit(provider)

result = asyncio.run(kit.consensus("What is 2+2?"))
print(result.value)
```

## Known Limitations

**No connection pooling (stdlib backend)**
The default HTTP backend opens a new TCP+TLS connection per LLM call. For
high-throughput workloads (e.g. `consensus` with many samples or long
`react_loop` chains), install `executionkit[http]` to enable the `httpx`
connection-pool backend.

**`react_loop` context growth**
The message history grows with every tool call round. For loops exceeding ~20
rounds or with many tools per round, set `max_history_messages` to avoid
hitting the model's context window limit.

**`consensus` exact-string matching**
Two responses that are semantically identical but differ in whitespace or
trailing newlines are counted as distinct votes. Use consistent prompt
formatting and low-temperature settings when exact agreement matters.

**Default evaluator in `refine_loop`**
The built-in quality scorer is a lightweight LLM prompt intended for
development use. Supply a custom `evaluator=` function for production
workloads or when input may contain adversarial content.

**No streaming support**
All completions are batch requests. Streaming responses are not currently
supported.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code style, and PR process.

## License

MIT. See [LICENSE](LICENSE).
