---
tags:
  - recipe
  - reliability
---

# Multi-provider failover on rate limits

When your primary provider returns `429`, fail over to a secondary without retrying the primary into the ground.

## The pattern

Wrap multiple `Provider` instances in a thin adapter that satisfies the `LLMProvider` protocol. Try the primary; on `RateLimitError`, fall through to the next.

```python
import asyncio
import os
from executionkit import (
    LLMProvider,
    LLMResponse,
    Provider,
    RateLimitError,
    consensus,
)

class FailoverProvider:
    """Try providers in order; fall through on RateLimitError."""

    def __init__(self, *providers: LLMProvider) -> None:
        if not providers:
            raise ValueError("FailoverProvider needs at least one provider")
        self._providers = providers
        # ToolCallingProvider check on the *first* provider's capability.
        self.supports_tools = getattr(providers[0], "supports_tools", False)

    async def complete(self, messages, **kwargs) -> LLMResponse:
        last_exc: Exception | None = None
        for p in self._providers:
            try:
                return await p.complete(messages, **kwargs)
            except RateLimitError as exc:
                last_exc = exc
                continue
        # All providers rate-limited: re-raise the most recent.
        assert last_exc is not None
        raise last_exc


async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    ) as primary, Provider(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
        model="llama-3.3-70b-versatile",
    ) as secondary:
        provider = FailoverProvider(primary, secondary)

        # Patterns accept any LLMProvider — no changes required.
        result = await consensus(
            provider,
            "Classify: 'My card was charged twice.' Answer one of: billing, tech, other.",
            num_samples=3,
        )
        print(result.value)
        print(result.cost)

asyncio.run(main())
```

## Why this works

- `LLMProvider` is a **structural protocol**. Any object with a matching `complete` method satisfies it — no inheritance required.
- `RateLimitError` is the only `LLMError` subclass we treat as "fall through." `PermanentError` (401/403/404) and `ProviderError` (5xx) are *not* caught here — they should fail loudly.
- Patterns like `consensus` will issue many parallel calls. Each individual call goes through `FailoverProvider.complete`, so each call independently tries the chain.
- If both providers rate-limit, the most recent `RateLimitError` is re-raised so the caller still sees `retry_after`.

## Variations

### Round-robin instead of strict order

```python
class RoundRobinProvider:
    def __init__(self, *providers: LLMProvider) -> None:
        self._providers = providers
        self._next = 0
        self.supports_tools = all(getattr(p, "supports_tools", False) for p in providers)

    async def complete(self, messages, **kwargs) -> LLMResponse:
        i = self._next
        self._next = (self._next + 1) % len(self._providers)
        return await self._providers[i].complete(messages, **kwargs)
```

### Don't fail over on 401 — surface immediately

`PermanentError` already isn't caught by the failover loop above, so authentication failures bubble straight up. That's the desired behavior — failing over after an invalid API key just hides the real problem.

### Cumulative cost across providers

`Provider.complete` returns an `LLMResponse` whose `usage` carries token counts. The patterns aggregate these into `result.cost` regardless of which provider answered. A `consensus` call that ran 3 samples on the primary and 2 on the secondary still reports a single `TokenUsage` total.

## Caveats

- **Don't wrap retry inside a retry.** ExecutionKit's per-call `RetryConfig` already retries `429`s with backoff. The failover here is for the case where retries are exhausted. If you want **immediate** failover with zero retries on the primary, pass `retry=RetryConfig(max_retries=0)` to the pattern.
- **`supports_tools` must be set correctly** for `react_loop` to accept the wrapped provider. The example takes the first provider's capability — adjust if your fleet is mixed.
- **Cost accounting still works,** because `LLMResponse.usage` is reported by whichever provider actually answered.

## Related

- [Provider Setup](../getting-started/providers.md) — configuring each upstream.
- [Cost-aware routing](cost-routing.md) — pick provider by request tier, not error.
