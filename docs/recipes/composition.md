---
tags:
  - recipe
  - composition
---

# Compose pattern calls

`pipe()` runs an unconditional sequence. It converts each step's `value` to a
string and passes that string to the next step.

The example extracts facts as JSON, then writes a short summary from those
facts:

```python
import asyncio
import os
from typing import Any

from executionkit import (
    LLMProvider,
    PatternResult,
    Provider,
    TokenUsage,
    pipe,
    refine_loop,
    structured,
)


def validate_facts(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "Expected a JSON object."
    if not isinstance(value.get("facts"), list):
        return "The 'facts' field must be an array."
    return None


async def extract_facts(
    provider: LLMProvider,
    prompt: str,
    *,
    max_cost: TokenUsage | None = None,
) -> PatternResult[Any]:
    return await structured(
        provider,
        "Extract only supported facts from this text. "
        f"Return {{\"facts\": [string, ...]}}.\n\n{prompt}",
        validator=validate_facts,
        max_retries=2,
        max_cost=max_cost,
    )


async def write_summary(
    provider: LLMProvider,
    prompt: str,
    *,
    max_cost: TokenUsage | None = None,
) -> PatternResult[str]:
    return await refine_loop(
        provider,
        "Write one concise paragraph using only the facts in this JSON. "
        f"Do not add facts.\n\n{prompt}",
        max_iterations=2,
        target_score=0.85,
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
            "The deployment began at 09:00 UTC. It completed at 09:12 UTC. "
            "No rollback was required.",
            extract_facts,
            write_summary,
            max_budget=TokenUsage(llm_calls=6),
        )
        print(result.value)
        print(result.cost)
        print(result.metadata["step_costs"])


asyncio.run(main())
```

## What `pipe()` guarantees

- Steps run in the supplied order.
- The same provider is passed to every step.
- Shared keyword arguments are filtered against each step's signature.
- `max_budget` is converted to each step's remaining `max_cost`.
- The final cost is the sum of all step costs.
- Metadata includes `step_count`, `step_metadata`, and `step_costs`.
- An `ExecutionKitError` carries cumulative cost and the completed
  `step_costs`.

Token budgets are checked before each call. A successful response can put its
token total above the configured amount; the next call is then blocked. The
LLM call count is reserved before dispatch and includes retry attempts.

## When not to use a pipe

Write a normal async function when a step can be skipped, repeated, routed to a
different provider, or compensated after failure. Use `Workflow` when named
steps have dependencies and independent ready steps should run concurrently.

See [Pipe](../patterns/pipe.md) for the full contract and
[Workflows and approvals](../guides/workflows.md) for dependency-based
execution.
