# Anthropic Message Batches

ExecutionKit has a native client for Anthropic's Message Batches API. Use it
for offline fan-out work where waiting for a batch job is acceptable.

This integration is separate from `Provider`:

- `Provider` calls an OpenAI-compatible live chat endpoint.
- `AnthropicBatchClient` calls Anthropic's native batch endpoints.

## Create a client

```python
import os

from executionkit import AnthropicBatchClient

client = AnthropicBatchClient(os.environ["ANTHROPIC_API_KEY"])
```

The default base URL is `https://api.anthropic.com`. The client sends the
Anthropic API version expected by this implementation and uses `urllib` in a
worker thread. It does not require the Anthropic SDK.

## Batch consensus

```python
from executionkit import consensus_batch

result = await consensus_batch(
    client,
    model="<anthropic-model-id>",
    prompt="Return only the ISO country code for France.",
    num_samples=5,
    strategy="majority",
    poll_interval=5.0,
    timeout=1_800.0,
)

print(result.value)
print(result.metadata["agreement_ratio"])
print(result.metadata["batch_id"])
print(result.cost)
```

`consensus_batch()` submits identical prompt entries in one batch. It uses the
same exact-text vote function as live `consensus()`.

## Batch map

```python
from executionkit import map_batch

result = await map_batch(
    client,
    model="<anthropic-model-id>",
    prompts=[
        "Summarize document A.",
        "Summarize document B.",
    ],
)

for response in result.value:
    print(response)
```

Responses are returned in prompt order even when the provider completes
entries in another order. `map_batch()` performs only the map operation; it
does not send a reduce prompt.

## Polling and timeout

Both helpers:

1. create a batch;
2. poll until the provider reports an ended state;
3. fetch the result file; and
4. parse every expected entry.

`poll_interval` controls the delay between status checks. `timeout` is a
wall-clock limit for waiting on the batch.

## Failure behavior

The helpers use all-or-nothing results:

- any non-succeeded entry raises `ProviderError`;
- a missing or duplicate `custom_id` raises `ProviderError`;
- missing batch IDs or result URLs raise `ProviderError`;
- HTTP 429 raises `RateLimitError` with `retry_after`; and
- a polling timeout raises `ProviderError`.

Successful entries are not returned when any entry fails. This prevents a
caller from silently treating an incomplete set as complete.

`result.cost.llm_calls` is the number of batch entries, not the number of HTTP
poll requests. Input and output tokens are summed across entries.

## Choose live or batch

| Need | Use |
|---|---|
| Interactive response latency | `consensus()` with a live provider |
| Provider-independent OpenAI-compatible endpoint | `consensus()` or `map_reduce()` |
| Offline Anthropic fan-out | `consensus_batch()` or `map_batch()` |
| A full map and reduce on a live endpoint | `map_reduce()` |

## Related

- [Batch API reference](../api/batches.md)
- [ADR-014](../adr/014-message-batches.md)
- [Consensus](../patterns/consensus.md)
- [Map-reduce](../patterns/map-reduce.md)
