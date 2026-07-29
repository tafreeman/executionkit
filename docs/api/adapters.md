# Providers and responses

## Built-in HTTP client

`Provider` appends `/chat/completions` to `base_url`, sends OpenAI-format JSON,
and parses OpenAI-format responses. It uses `urllib` in the base install and
an `httpx.AsyncClient` when the `httpx` extra is installed.

::: executionkit.provider.Provider

## Provider protocols

These are structural protocols. A custom provider does not need to inherit
from them, but its methods and attributes must have compatible signatures.

::: executionkit.provider.LLMProvider

::: executionkit.provider.ToolCallingProvider

::: executionkit.provider.StreamingProvider

At runtime, a `@runtime_checkable` protocol checks whether required attributes
exist; it does not validate the full type signature. Run a static type checker
and integration tests for custom adapters.

Set `supports_tools = True` only when the adapter can send OpenAI-format tool
schemas and parse tool calls. `react_loop()` rejects a provider when the flag
is absent or false.

## Response types

::: executionkit.provider.LLMResponse

::: executionkit.provider.ToolCall

`LLMResponse.raw` is the unmodified provider payload. ExecutionKit does not
emit it in package-owned traces. Caller code must redact it before logging.

`LLMResponse.usage` accepts these token field names:

- `prompt_tokens` and `completion_tokens`; or
- `input_tokens` and `output_tokens`.

Missing usage fields count as zero. Boolean, negative, or implausibly large
counts raise `ProviderError` when the properties are read.

## Test provider

::: executionkit._mock.MockProvider

Import it from the package root:

```python
from executionkit import MockProvider

provider = MockProvider(responses=["draft", "final"])
```

It records calls and returns scripted responses without network access.

## Adapter checklist

A custom adapter should:

1. accept OpenAI-format message dictionaries;
2. translate pattern options such as `temperature`, `max_tokens`, and `tools`;
3. return `LLMResponse`;
4. translate provider tool calls into `ToolCall`;
5. report token usage when available;
6. map retryable and non-retryable failures to the appropriate ExecutionKit
   exception; and
7. test basic calls, tools, streaming, cancellation, timeout, and malformed
   responses separately.

See [Provider setup](../getting-started/providers.md) for a complete custom
adapter skeleton.
