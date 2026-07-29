---
tags:
  - recipe
  - reliability
---

# Fail over between providers

This adapter tries providers in order and moves to the next provider only when
the current provider raises `RateLimitError`.

```python
import asyncio
import os
from collections.abc import Sequence
from typing import Any

from executionkit import (
    LLMProvider,
    LLMResponse,
    Provider,
    RateLimitError,
    consensus,
)


class FailoverProvider:
    """Try each provider until one completes the request."""

    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = tuple(providers)

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        last_error: RateLimitError | None = None

        for provider in self._providers:
            try:
                return await provider.complete(messages, **kwargs)
            except RateLimitError as error:
                last_error = error

        assert last_error is not None
        raise last_error


async def main() -> None:
    async with Provider(
        base_url=os.environ["PRIMARY_BASE_URL"],
        api_key=os.environ["PRIMARY_API_KEY"],
        model=os.environ["PRIMARY_MODEL"],
    ) as primary, Provider(
        base_url=os.environ["SECONDARY_BASE_URL"],
        api_key=os.environ["SECONDARY_API_KEY"],
        model=os.environ["SECONDARY_MODEL"],
    ) as secondary:
        provider = FailoverProvider([primary, secondary])
        result = await consensus(
            provider,
            "Classify this request as billing, technical, or other: "
            "'My card was charged twice.'",
            num_samples=3,
        )
        print(result.value)
        print(result.cost)


asyncio.run(main())
```

`LLMProvider` is a structural protocol. The adapter does not inherit from an
ExecutionKit class; its `complete()` method is enough for patterns that do not
use tools or streaming.

## Failure behavior

- Authentication errors, invalid requests, and provider failures are not
  caught. The caller sees the original error.
- If every provider is rate-limited, the adapter raises the last
  `RateLimitError`.
- A pattern's `RetryConfig` applies when the entire failover chain fails. Each
  retry starts at the first provider again.
- `result.cost` contains usage returned by the provider that completed each
  call. Failed attempts can count as LLM calls, but usually have no token usage
  because the provider did not return it.

## Tool calls and streaming

The adapter above implements only `LLMProvider`. Do not mark it as supporting
tools or streaming unless it also implements and delegates those protocol
methods. A mixed provider list also needs an explicit policy for differing tool
schemas and streaming behavior.

For proactive provider selection, use [`Router`](cost-routing.md). For
per-attempt pacing and retry settings, see
[Execution controls](../guides/execution-controls.md).
