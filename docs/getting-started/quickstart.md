# Quick start

This guide runs a three-sample consensus call and then shows the return value,
other patterns, and synchronous wrappers.

## 1. Install

```bash
python -m pip install executionkit
```

Set credentials and a model for your endpoint. For example:

=== "macOS or Linux"

    ```bash
    export OPENAI_API_KEY="<your-key>"
    export OPENAI_MODEL="<your-model>"
    ```

=== "PowerShell"

    ```powershell
    $env:OPENAI_API_KEY = "<your-key>"
    $env:OPENAI_MODEL = "<your-model>"
    ```

## 2. Run a pattern

Save this as `quickstart.py`:

```python
import asyncio
import os

from executionkit import Provider, consensus


async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ["OPENAI_MODEL"],
    ) as provider:
        result = await consensus(
            provider,
            "Return only the ISO country code for France.",
            num_samples=3,
        )

        print(result.value)
        print(result.score)
        print(result.cost)
        print(dict(result.metadata))


asyncio.run(main())
```

Run it:

```bash
python quickstart.py
```

The exact token counts depend on the endpoint. A typical result has this shape:

```text
FR
1.0
TokenUsage(input_tokens=..., output_tokens=..., llm_calls=3)
{'agreement_ratio': 1.0, 'unique_responses': 1, 'tie_count': 1}
```

`llm_calls` counts dispatched attempts. A retry increases the count.

When the `httpx` extra is installed, the async context manager closes its
connection pool. With the standard-library transport there is no persistent
client, but using the same context-manager form keeps application code
consistent.

## 3. Use a local endpoint

For a local Ollama server, change only the provider construction:

```python
provider = Provider(
    base_url="http://localhost:11434/v1",
    model="<installed-ollama-model>",
)
```

No API key is needed for a default local Ollama installation. See
[Provider setup](providers.md) for other endpoints and their limits.

## 4. Choose another pattern

### Iterative refinement

```python
from executionkit import refine_loop

result = await refine_loop(
    provider,
    "Explain gradient descent to a new software engineer.",
    target_score=0.85,
    max_iterations=3,
)
```

The default evaluator makes an additional model call for each generated
answer. Use a caller-supplied evaluator when you need a predictable scoring
rule.

### Tool loop

```python
from executionkit import Tool, react_loop


async def get_status(service: str) -> str:
    return f"{service}: operational"


status_tool = Tool(
    name="get_status",
    description="Return the status of a named service.",
    parameters={
        "type": "object",
        "properties": {"service": {"type": "string"}},
        "required": ["service"],
        "additionalProperties": False,
    },
    execute=get_status,
    timeout=5.0,
)

result = await react_loop(
    provider,
    "Check the status of the billing service.",
    tools=[status_tool],
)
```

Only register tools you trust. `react_loop()` validates and bounds the
model-to-tool call, but the tool body runs with the current process's
permissions.

### Structured output

```python
from executionkit import structured


def validate(value: object) -> str | None:
    if not isinstance(value, dict):
        return "Expected a JSON object."
    if not isinstance(value.get("priority"), int):
        return "'priority' must be an integer."
    return None


result = await structured(
    provider,
    "Return JSON with an integer 'priority' for this ticket: payment failed.",
    validator=validate,
)
```

## 5. Track several calls

`Kit` stores cumulative usage and can also hold a conversation transcript:

```python
from executionkit import Kit

kit = Kit(provider)
await kit.consensus("Return only 'yes' or 'no': is 7 prime?", num_samples=3)
await kit.refine("Explain why 7 is prime.", max_iterations=2)
print(kit.usage)
```

## 6. Call from synchronous code

```python
from executionkit import consensus_sync

result = consensus_sync(provider, "Return only the result of 2 + 2.")
print(result.value)
```

Sync wrappers call `asyncio.run()`. They raise `RuntimeError` inside an already
running event loop, including async web handlers and most notebook kernels. Use
`await` in those environments.

## Next

- [Patterns overview](../patterns/index.md)
- [Execution controls](../guides/execution-controls.md)
- [API index](../api/index.md)
