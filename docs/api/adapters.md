# Adapters

The provider layer: HTTP client, structural protocols, and response types.

## `Provider`

The default OpenAI-compatible HTTP client. Speaks `/chat/completions` JSON. Uses stdlib `urllib` by default; switches to `httpx.AsyncClient` (with connection pooling) when `httpx` is installed.

::: executionkit.provider.Provider

## Protocols

`LLMProvider` and `ToolCallingProvider` are `@runtime_checkable` `Protocol`s. Any object matching the interface satisfies the protocol — no inheritance required.

::: executionkit.provider.LLMProvider

::: executionkit.provider.ToolCallingProvider

## Response types

::: executionkit.provider.LLMResponse

::: executionkit.provider.ToolCall

## MockProvider

For unit tests. Yields canned responses, tracks all calls, and never makes real HTTP calls.

::: executionkit._mock.MockProvider

## Custom adapter checklist

Implement a custom provider in three steps:

1. **Define a class with an async `complete` method** matching `LLMProvider`:

   ```python
   from executionkit.provider import LLMResponse

   class MyProvider:
       async def complete(
           self,
           messages,
           *,
           temperature=None,
           max_tokens=None,
           tools=None,
           **kwargs,
       ) -> LLMResponse:
           ...
   ```

2. **Return `LLMResponse(content=..., usage={...})`.** `usage` should be a dict with at least `input_tokens` and `output_tokens` so cost tracking works. Empty dict is acceptable (cost will be `0`).

3. **For tool calling, set `supports_tools = True`** and populate `LLMResponse.tool_calls` from the upstream response. `react_loop` will refuse providers without `supports_tools=True`.

The structural-protocol design means **no registration step** — pass your provider directly to any pattern.

## Notes on the default `Provider`

- **API key masking.** `Provider.__repr__` always shows `api_key='***'` regardless of the actual key length or prefix. Keys are never written to repr output, log lines, or exception messages.
- **Credential redaction in errors.** HTTP error messages are scanned for credential-shaped substrings (matching `sk-...`, `bearer ...`, `token=...`, etc.) and redacted to `[REDACTED]` before being raised.
- **Connection lifecycle.** `Provider` supports `async with` and `await provider.aclose()`. With the `httpx` backend, this closes the underlying `AsyncClient` cleanly.
- **Retries are at the call layer**, not the HTTP layer. Use `RetryConfig` on the pattern call (e.g. `consensus(..., retry=RetryConfig(...))`).
