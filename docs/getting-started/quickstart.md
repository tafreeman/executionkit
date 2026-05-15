# Quick Start

Five lines from install to a working consensus call.

## 1. Install

```bash
pip install executionkit
export OPENAI_API_KEY=sk-...
```

## 2. Your first pattern

```python
import asyncio
import os
from executionkit import Provider, consensus

async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    ) as provider:
        result = await consensus(
            provider,
            "What is the capital of France? Answer in one word.",
            num_samples=3,
        )
        print(result.value)                          # Paris
        print(result.metadata["agreement_ratio"])    # 1.0
        print(result.cost)                           # TokenUsage(input_tokens=..., output_tokens=..., llm_calls=3)

asyncio.run(main())
```

When `httpx` is installed, `Provider` creates an `httpx.AsyncClient` at construction time; the async context manager closes it cleanly. With the default stdlib backend, there is no persistent client. You can also call `await provider.aclose()` directly.

## 3. Pick a different pattern

=== "Iterative refinement"

    ```python
    from executionkit import refine_loop

    result = await refine_loop(
        provider,
        "Write a one-paragraph summary of the Turing test.",
        target_score=0.85,
        max_iterations=4,
    )
    print(result.value)                          # Best response found
    print(result.score)                          # 0.91
    print(result.metadata["iterations"])         # 2
    ```

=== "ReAct tool loop"

    ```python
    from executionkit import Tool, react_loop

    async def get_weather(city: str) -> str:
        return f"Weather in {city}: 18°C, light rain."

    weather = Tool(
        name="get_weather",
        description="Look up current weather for a city.",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
            "additionalProperties": False,
        },
        execute=get_weather,
    )

    result = await react_loop(provider, "What's the weather in Paris?", tools=[weather])
    print(result.value)
    print(result.metadata["tool_calls_made"])    # 1
    ```

=== "Compose patterns"

    ```python
    from functools import partial
    from executionkit import pipe, consensus, refine_loop

    result = await pipe(
        provider,
        "Explain gradient descent in simple terms.",
        partial(consensus, num_samples=3),
        partial(refine_loop, target_score=0.9),
    )
    print(result.value)
    print(result.cost)                           # Cumulative across both steps
    ```

## 4. Track cost across calls

```python
from executionkit import Kit

kit = Kit(provider)
await kit.consensus("Classify: ...", num_samples=3)
await kit.refine("Summarise: ...")
print(kit.usage)            # TokenUsage(input_tokens=..., output_tokens=..., llm_calls=...)
```

## 5. Sync wrappers (outside async)

```python
from executionkit import consensus_sync

result = consensus_sync(provider, "What is 2 + 2?")
print(result.value)
```

The sync wrappers raise `RuntimeError` when called inside a running event loop (e.g. Jupyter) — use `await` directly there.

## What next

- [Provider Setup](providers.md) — configure OpenAI, Ollama, Groq, Together, GitHub Models, and Azure via a gateway.
- [Patterns Overview](../patterns/index.md) — pick the right pattern for your problem.
- [Recipes](../recipes/composition.md) — failover, cost-aware routing, pattern chaining.
