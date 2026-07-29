# Execution controls

This guide covers call budgets, retries, pacing, cost estimates, cumulative
usage, and traces. These controls measure or limit execution; they do not
measure answer quality.

## Call and token budgets

Patterns accept `max_cost=TokenUsage(...)`. `pipe()` accepts the same idea as
`max_budget`.

```python
from executionkit import TokenUsage, consensus

result = await consensus(
    provider,
    "Return only 'yes' or 'no': is 17 prime?",
    num_samples=5,
    max_cost=TokenUsage(
        input_tokens=5_000,
        output_tokens=1_000,
        llm_calls=8,
    ),
)
```

Budget fields use these values:

| Value | Meaning in a budget |
|---:|---|
| `0` | No limit for this field. |
| Positive integer | Stop dispatching once recorded usage reaches the value. |
| `-1` | Internal `pipe()` marker for a field exhausted by a prior step. Do not set it in application code. |

Call accounting is strict within one asyncio event loop. The package checks and
reserves a call slot without an `await` between those operations, so concurrent
samples cannot claim the same remaining slot. Every dispatched retry reserves
another slot.

Token limits are checked before a call, using usage reported by completed
responses. The package cannot know the next response's actual token count
before dispatch. A successful response can therefore take the recorded total
past an input- or output-token limit; the limit blocks the next call. If you
need a hard per-response output bound, also set `max_tokens`.

`CostTracker` and the budget sequence are designed for one asyncio event loop.
They are not thread-safe.

## Retries

```python
from executionkit import ProviderError, RateLimitError, RetryConfig

retry = RetryConfig(
    max_retries=2,
    base_delay=0.5,
    max_delay=10.0,
    exponential_base=2.0,
    retryable=(RateLimitError, ProviderError),
)

result = await consensus(provider, prompt, retry=retry)
```

`max_retries` counts attempts after the initial call:

| Value | Maximum dispatched attempts |
|---:|---:|
| `0` | 1 |
| `1` | 2 |
| `3` (the default) | 4 |

Retry delays use full jitter from zero to the capped exponential delay.
`PermanentError` is not retried by the default configuration.
`asyncio.CancelledError` propagates immediately.

Transport retries and pattern retries are different:

- `RetryConfig` repeats a failed provider call.
- `structured(max_retries=...)` asks the model to repair invalid JSON.
- `refine_loop(max_iterations=...)` asks for revised content.

All of them can add model calls.

## Rate control

`TokenBucket` has two integration points with different scopes.

### Pace top-level `Kit` methods

```python
from executionkit import Kit, TokenBucket

kit = Kit(
    provider,
    rate_limiter=TokenBucket(rate=2.0, capacity=4.0),
)
```

This acquires one token before each call to a `Kit` pattern method. A single
`kit.consensus()` call acquires one token even though the pattern may dispatch
several provider calls.

### Pace each provider attempt

```python
bucket = TokenBucket(rate=2.0, capacity=4.0)
retry = RetryConfig(rate_limit_strategy=bucket)

result = await consensus(provider, prompt, retry=retry)
```

This acquires one token before every initial provider attempt and retry. When a
`RateLimitError` includes `retry_after`, the bucket starts a cooldown before
the next acquisition.

Do not attach the same bucket at both levels unless you intentionally want both
limits.

## Cumulative usage

`Kit` adds the cost of calls made through its methods:

```python
from executionkit import Kit

kit = Kit(provider)
first = await kit.consensus("Return only the result of 6 * 7.", num_samples=3)
second = await kit.refine("Explain that result.", max_iterations=2)

print(first.cost)
print(second.cost)
print(kit.usage)
```

When an `ExecutionKitError` carries partial cost, `Kit` records that cost before
re-raising. Calls made directly through `kit.provider` are not included.

## Estimate money from token counts

ExecutionKit does not include a model-price table. Supply current per-token
rates from the provider and account tier you use:

```python
import os

from executionkit import estimate_cost

input_rate = float(os.environ["MODEL_INPUT_RATE_PER_TOKEN"])
output_rate = float(os.environ["MODEL_OUTPUT_RATE_PER_TOKEN"])
estimated = estimate_cost(
    result.cost,
    input_rate=input_rate,
    output_rate=output_rate,
)
```

The function performs arithmetic only. It does not validate rates, currencies,
discounts, cached-token pricing, or model names.

## Trace execution

Pass a sync or async callback with `trace=`:

```python
from executionkit import TraceEvent, consensus


async def handle_trace(event: TraceEvent) -> None:
    print(event.kind, dict(event.payload))


result = await consensus(provider, prompt, trace=handle_trace)
```

Built-in event kinds include:

- `llm_call_start`, `llm_call_end`, and `llm_call_error`;
- `tool_call_start` and `tool_call_end`;
- `workflow_step_start` and `workflow_step_end`; and
- `plan_step_start` and `plan_step_end`.

Package-owned LLM traces redact credential-shaped text before emitting
response content. Tool-start traces include argument keys and redact values by
default. Treat trace callbacks as a data-export boundary anyway: caller-owned
callbacks can log or transmit every payload they receive.

When the `otel` extra is installed, `executionkit.observability.llm_span()` and
`record_llm_span_attributes()` can add spans to an application-configured
OpenTelemetry SDK. The package does not configure an exporter.

## Related

- [Configuration defaults](../api/configuration.md)
- [Execution helper API](../api/execution.md)
- [Streaming cost timing](streaming.md)
