---
tags:
  - pattern
  - composition
---

# Pipe (Composition)

`pipe()` chains reasoning patterns into a sequence. The `value` of each step is converted to a string and used as the prompt for the next. Costs accumulate, and an optional shared `max_budget` is forwarded to every step as `max_cost=`.

## When to use / when not to use

| Use it when… | Avoid it when… |
|--------------|----------------|
| Your task is two or three sequential steps (e.g. "consensus then refine"). | You need branching, retries, or conditional steps — use a workflow runtime. |
| You want **one** cumulative cost number across all steps. | The intermediate outputs need to be consumed independently. |
| You want a shared budget enforced across the chain. | Steps need different providers — pipe uses a single provider per chain. |

## Call flow

```mermaid
sequenceDiagram
    participant App
    participant pipe
    participant Step1 as Step 1 (consensus)
    participant Step2 as Step 2 (refine_loop)
    App->>pipe: pipe(provider, prompt, consensus, refine_loop, max_budget=B)
    pipe->>Step1: step(provider, prompt, max_cost=B)
    Step1-->>pipe: result1
    pipe->>pipe: total_cost += result1.cost; remaining = B - total_cost
    pipe->>Step2: step(provider, str(result1.value), max_cost=remaining)
    Step2-->>pipe: result2
    pipe-->>App: PatternResult(value=result2.value, cost=total_cost, ...)
```

## Minimal example

```python
import asyncio
import os
from functools import partial
from executionkit import Provider, consensus, pipe, refine_loop

async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    ) as provider:
        result = await pipe(
            provider,
            "Explain gradient descent in simple terms.",
            partial(consensus, num_samples=3),
            partial(refine_loop, target_score=0.9, max_iterations=2),
        )

        print(result.value)                                 # final refined answer
        print(result.cost)                                  # cumulative across both steps
        print(result.metadata["step_count"])                # 2
        print(result.metadata["step_metadata"])             # [consensus_meta, refine_meta]

asyncio.run(main())
```

`functools.partial` is the idiomatic way to pre-bind per-step kwargs. `pipe` itself filters its `**shared_kwargs` to keys each step actually accepts, so you can pass `max_cost=` once and have it forwarded only to steps that declare it.

## Configuration knobs

| Parameter | Default | Description |
|-----------|---------|-------------|
| `*steps` | — | One or more async pattern callables. Each must accept `(provider, prompt, **kwargs)`. |
| `max_budget` | `None` | Optional shared `TokenUsage` ceiling forwarded to each step as `max_cost`. |
| `**shared_kwargs` | — | Extra kwargs forwarded to every step (filtered to each step's signature). |

## Metadata keys

| Key | Type | Meaning |
|-----|------|---------|
| `step_count` | `int` | Number of steps in the chain. |
| `step_metadata` | `list[dict]` | Each step's metadata, in order. |
| (final step keys) | — | The last step's metadata is also merged in at the top level. |

## Budget arithmetic

When `max_budget` is set, `pipe` computes `remaining = max_budget - total_cost` after each step and passes that as `max_cost=` to the next:

| Field convention | Meaning |
|------------------|---------|
| `0` | "No limit" — preserved as-is. |
| `> 0` | Tokens / calls still available. |
| `-1` | Field was limited and is now exhausted. (Not `0`, to avoid being misread as "unlimited".) |

This means a single `max_budget=TokenUsage(input_tokens=10_000, output_tokens=2_000, llm_calls=20)` enforces an end-to-end ceiling across the chain. If any step would push past it, that step raises `BudgetExhaustedError` carrying the accumulated cost.

## Cost characteristics

- **Sum of step costs.** No additional LLM calls beyond what the steps themselves make.
- **Sequential by definition** — each step's input is the previous step's output.
- **Errors propagate with cumulative cost.** If a step raises `ExecutionKitError`, `pipe` adds `total_cost` to the exception's `.cost` before re-raising.

## Empty chain

`pipe(provider, prompt)` with no steps returns `PatternResult(value=prompt)` with zero cost — useful as a no-op default.

## Source

[`executionkit/compose.py`](https://github.com/tafreeman/executionkit/blob/main/executionkit/compose.py)
