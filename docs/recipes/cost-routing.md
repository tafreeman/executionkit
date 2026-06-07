---
tags:
  - recipe
  - cost
---

# Cost-aware provider routing

Premium-tier requests go to a strong model (e.g. `gpt-4o`); cheap requests go to a small fast model (e.g. `claude-3-5-haiku-latest` via proxy, or `llama-3.3-70b` on Groq). Pick at call time without changing the pattern code.

## The pattern

Route at the *outer* level — the pattern call. Each request carries a tier; `Router` picks the right `Provider`.

```python
import asyncio
import os
from typing import Literal
from executionkit import Provider, RouteRule, Router, consensus, refine_loop

Tier = Literal["premium", "cheap"]

async def answer(router: Router, tier: Tier, prompt: str) -> str:
    provider = router.select(prompt, tier=tier)
    if tier == "premium":
        # High-quality path: refine until target score.
        result = await refine_loop(provider, prompt, target_score=0.9, max_iterations=3)
    else:
        # Cheap path: single-shot consensus with 3 samples on a fast model.
        result = await consensus(provider, prompt, num_samples=3)

    return result.value


async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o",
    ) as premium, Provider(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
        model="llama-3.3-70b-versatile",
    ) as cheap:
        router = Router(
            rules=[
                RouteRule(
                    "premium-tier",
                    premium,
                    lambda prompt, context: context.get("tier") == "premium",
                )
            ],
            fallback=cheap,
        )

        # Free-tier user — fast, cheap path
        print(await answer(router, "cheap", "What is 7 * 8?"))

        # Paying customer — high-quality path
        print(await answer(router, "premium",
                           "Draft a one-paragraph project status update for stakeholders."))

asyncio.run(main())
```

## Why this works

- ExecutionKit patterns take a `provider` as their first argument. Swapping providers is a single positional argument — no pattern code changes.
- Each `Provider` has its own `base_url`, `api_key`, and `model`. They are **independent HTTP clients** (especially when `httpx` is installed — each gets its own connection pool).
- Routing happens *before* the pattern call. The pattern doesn't know or care about the tier.
- `Router.run(pattern, prompt, **kwargs)` is available when one selected provider should call one pattern directly. Select explicitly when you want different patterns per route, as above.

## Variations

### Per-step routing inside `pipe`

You can route by *step* instead of by *request*. `pipe` only passes one provider, so for true per-step provider swapping, write a thin step that uses a closure:

```python
from executionkit import pipe, consensus, refine_loop

async def cheap_consensus(_: object, prompt: str, **kw):
    return await consensus(cheap, prompt, num_samples=3, **kw)

async def premium_refine(_: object, prompt: str, **kw):
    return await refine_loop(premium, prompt, target_score=0.9, **kw)

# The `provider` arg is unused — each step uses its bound provider.
result = await pipe(
    cheap,                           # placeholder, unused by the steps
    "Explain gradient descent.",
    cheap_consensus,
    premium_refine,
)
```

### Route by token budget

Pass the routing decision through `max_cost`. If a request comes with a tight `TokenUsage` ceiling, route it to the cheap provider:

```python
def pick(cheap: Provider, premium: Provider, budget: TokenUsage | None) -> Provider:
    if budget and budget.input_tokens > 0 and budget.input_tokens < 1_000:
        return cheap
    return premium
```

### Route by content

For "premium-when-it-matters," classify the prompt with the cheap provider first, then route. This is `pipe` with a router step — but since pipe doesn't branch, write it as a plain async function:

```python
async def smart_route(cheap: Provider, premium: Provider, prompt: str) -> str:
    # Tiny classifier call on the cheap provider
    tag = await consensus(
        cheap,
        f"Classify this user request as 'simple' or 'complex'. "
        f"Answer one word.\n\n{prompt}",
        num_samples=3,
    )
    provider = premium if tag.value.strip().lower() == "complex" else cheap
    answer = await refine_loop(provider, prompt, target_score=0.85)
    return answer.value
```

The cheap classifier costs `~3 small calls`; the routing payoff is hours of saved premium spend if most requests are simple.

## Caveats

- **Cost is reported per-call, not per-tier.** If you need per-tier accounting, sum `result.cost` into separate buckets at your application layer.
- **Different providers have different rate limits and latency.** Groq is fast and cheap but stricter on RPM; OpenAI is slower but more permissive. Adjust `max_concurrency` per provider.
- **Don't route on `result.score` after the fact** — by then you've already paid. Either route on the input, or use `refine_loop` and let it converge instead of over-shooting.

## Related

- [Multi-provider failover](failover.md) — fall through on `RateLimitError` regardless of tier.
- [Combining patterns](composition.md) — pipe consensus into refine on the premium tier.
