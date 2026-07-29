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


async def explain_label(provider, prompt, *, max_cost=None):
    return await refine_loop(
        provider,
        f"Explain the support category {prompt!r} in one sentence.",
        target_score=0.85,
        max_iterations=2,
        max_cost=max_cost,
    )


async def main() -> None:
    async with Provider(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ["LLM_MODEL"],
    ) as provider:
        result = await pipe(
            provider,
            "Classify this request as billing, technical, or other: "
            "'My card was charged twice.'",
            partial(consensus, num_samples=3),
            explain_label,
        )

        print(result.value)
        print(result.cost)
        print(result.metadata["step_count"])
        print(result.metadata["step_metadata"])
        print(result.metadata["step_costs"])

asyncio.run(main())
```

`functools.partial` binds settings to one step. `pipe()` also filters its
shared keyword arguments to names accepted by each step.

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `*steps` | — | One or more async pattern callables. Each must accept `(provider, prompt, **kwargs)`. |
| `max_budget` | `None` | Optional shared `TokenUsage` budget forwarded to each step as `max_cost`. |
| `**shared_kwargs` | — | Extra kwargs forwarded to every step (filtered to each step's signature). |

## Metadata keys

| Key | Type | Meaning |
|-----|------|---------|
| `step_count` | `int` | Number of steps in the chain. |
| `step_metadata` | `list[dict]` | Each step's metadata, in order. |
| `step_costs` | `tuple[TokenUsage, ...]` | Cost of each step in order. Also attached to `ExecutionKitError.metadata` on failure. |
| (final step keys) | — | The last step's metadata is also merged in at the top level. |

## Budget arithmetic

When `max_budget` is set, `pipe` computes `remaining = max_budget - total_cost` after each step and passes that as `max_cost=` to the next:

| Field convention | Meaning |
|------------------|---------|
| `0` | "No limit" — preserved as-is. |
| `> 0` | Tokens / calls still available. |
| `-1` | Field was limited and is now exhausted. (Not `0`, to avoid being misread as "unlimited".) |

This means a single
`max_budget=TokenUsage(input_tokens=10_000, output_tokens=2_000, llm_calls=20)`
passes the remaining values to each step. Call limits are reserved before
dispatch. Token limits are checked against completed responses, so one response
can take a token total past its limit before the next step is blocked.

## Cost characteristics

- **Sum of step costs.** No additional LLM calls beyond what the steps themselves make.
- **Sequential by definition** — each step's input is the previous step's output.
- **Errors propagate with cumulative cost.** If a step raises `ExecutionKitError`, `pipe` adds `total_cost` to the exception's `.cost` before re-raising.
- **Unknown shared keywords may be dropped.** If a step does not accept
  `**kwargs`, `pipe` forwards only names present in its inspected signature.
  Validate custom step configuration in tests.

## Empty chain

`pipe(provider, prompt)` with no steps returns `PatternResult(value=prompt)` with zero cost — useful as a no-op default.

## Source

[`executionkit/compose.py`](https://github.com/tafreeman/executionkit/blob/main/executionkit/compose.py)
