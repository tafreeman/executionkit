# Streaming

ExecutionKit streams one provider generation as an async iterator. Algorithms
that need complete responses before they can continue are not streamed.

## Stream one generation

```python
from executionkit import Kit

kit = Kit(provider)
result = await kit.stream_consensus(
    "Explain a Python context manager in two sentences."
)

async for chunk in result.text_stream:
    print(chunk, end="", flush=True)

print()
print(result.cost)
```

Despite its name, `stream_consensus()` does not run consensus voting. Voting
requires complete samples to compare, so the method streams one call.

`stream_react_loop()` also streams one call:

```python
result = await kit.stream_react_loop("Write a short status update.")
async for chunk in result.text_stream:
    print(chunk, end="")
```

The method accepts `tools` for signature similarity with `Kit.react()`, but it
does not execute them. A streamed tool-call response may contain no useful text
delta.

## Cost is final after consumption

`StreamingPatternResult.cost` is a live view of recorded usage. Providers
normally report final token counts at the end of the stream. Read cost after
the `async for` loop has finished.

When streaming through `Kit`, the stream's recorded usage is added to
`kit.usage` when iteration ends or the iterator is closed. If a provider does
not emit a final usage frame, token counts may remain zero even though the
reserved call count is present.

## Unsupported pattern flags

These functions reject `stream=True`:

- `structured()`, because parsing and validation require the complete text;
- `map_reduce()`, because the reduce call needs all mapped outputs.

`consensus()`, `refine_loop()`, `react_loop()`, and `pipe()` do not expose a
stream flag. Use their normal async return values when you need the complete
algorithm.

## Provider requirements

A streaming adapter must satisfy `StreamingProvider`:

```python
from collections.abc import AsyncIterator


def stream(
    messages,
    *,
    temperature=None,
    max_tokens=None,
    tools=None,
    usage_sink=None,
    **kwargs,
) -> AsyncIterator[str]:
    ...
```

The built-in `Provider` parses OpenAI-format server-sent events. Endpoint
support varies. Test:

- normal text deltas;
- the provider's end marker;
- a final usage frame;
- timeout and cancellation;
- HTTP 429 and server errors; and
- malformed event data.

## Tool-using applications

For a turn that may need tools:

1. run `Kit.turn()` or `react_loop()` to completion;
2. report progress through a trace callback; and
3. stream a later text-only generation only if the additional call is useful.

Do not show a streamed draft as the result of a tool loop that has not
executed.

## Related

- [Conversational assistant recipe](../recipes/assistant.md)
- [Providers and responses](../api/adapters.md)
- [Execution controls](execution-controls.md)
