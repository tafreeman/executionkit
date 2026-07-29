---
tags:
  - recipe
  - routing
---

# Route requests by an application policy

`Router` selects a provider before a pattern starts. The decision is based on
ordered predicates supplied by the application.

```python
import asyncio
import os
from typing import Literal

from executionkit import Provider, RouteRule, Router, consensus

ServiceTier = Literal["standard", "reviewed"]


async def answer(router: Router, tier: ServiceTier, prompt: str) -> str:
    result = await router.run(
        consensus,
        prompt,
        context={"tier": tier},
        num_samples=3,
    )
    return result.value


async def main() -> None:
    async with Provider(
        base_url=os.environ["STANDARD_BASE_URL"],
        api_key=os.environ["STANDARD_API_KEY"],
        model=os.environ["STANDARD_MODEL"],
    ) as standard, Provider(
        base_url=os.environ["REVIEW_BASE_URL"],
        api_key=os.environ["REVIEW_API_KEY"],
        model=os.environ["REVIEW_MODEL"],
    ) as reviewed:
        router = Router(
            rules=[
                RouteRule(
                    name="reviewed-tier",
                    provider=reviewed,
                    predicate=lambda _prompt, context: (
                        context.get("tier") == "reviewed"
                    ),
                )
            ],
            fallback=standard,
        )

        print(await answer(router, "standard", "Summarize the incident."))
        print(await answer(router, "reviewed", "Review the release decision."))


asyncio.run(main())
```

Rules run in order. The first true predicate wins. If no predicate matches,
`fallback` is used.

Routing inputs belong in `context`. Pattern arguments such as `num_samples`
remain keyword arguments to `Router.run()`. ExecutionKit keeps those two
inputs separate so a routing key cannot be passed accidentally to the pattern.

## Choose a different pattern after routing

Call `select()` directly when the route also determines which pattern runs:

```python
from executionkit import Router, consensus, refine_loop


async def review(
    router: Router,
    prompt: str,
    *,
    needs_revision: bool,
) -> str:
    provider = router.select(prompt, needs_revision=needs_revision)

    if needs_revision:
        result = await refine_loop(
            provider,
            prompt,
            max_iterations=2,
            target_score=0.85,
        )
    else:
        result = await consensus(provider, prompt, num_samples=3)

    return result.value
```

## Cost policy belongs to the caller

ExecutionKit does not include provider prices or model rankings. If routing is
based on money, latency, residency, or account limits, load current values from
your own configuration. Record `result.cost` with the selected route so the
application can report usage by policy.

Predicates are normal caller functions. Keep them fast, deterministic, and
free of network calls. Use an explicit async classification step before
routing when the decision itself needs a model call.

For reactive failover, see [Fail over between providers](failover.md). For a
fixed multi-step sequence, see [Compose pattern calls](composition.md).
