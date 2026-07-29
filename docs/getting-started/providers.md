# Provider setup

`Provider` sends:

```text
POST {base_url}/chat/completions
Authorization: Bearer {api_key}
Content-Type: application/json
```

The request and response use the OpenAI chat-completions shape. The endpoint
must return a `choices` array with message content and may return OpenAI- or
Anthropic-style token-usage fields.

ExecutionKit does not discover models or translate native provider formats.
Choose a model supported by the endpoint and test the features you need.

## OpenAI

```python
import os

from executionkit import Provider

provider = Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model=os.environ["OPENAI_MODEL"],
)
```

## Ollama

Ollama exposes an OpenAI-compatible endpoint at `/v1`:

```python
provider = Provider(
    base_url="http://localhost:11434/v1",
    model="<installed-model>",
)
```

See the
[Ollama OpenAI-compatibility guide](https://docs.ollama.com/api/openai-compatibility).

## vLLM

```python
provider = Provider(
    base_url="http://localhost:8000/v1",
    api_key=os.environ.get("VLLM_API_KEY", ""),
    model="<served-model-id>",
)
```

See the
[vLLM OpenAI-compatible server guide](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html).

## llama.cpp

```python
provider = Provider(
    base_url="http://localhost:8080/v1",
    model="<server-model-id>",
)
```

The selected model needs a compatible chat template. See the
[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#post-v1chatcompletions-openai-compatible-chat-completions-api).

## GitHub Models

GitHub Models uses the current `models.github.ai` inference endpoint and model
IDs in `publisher/model` form:

```python
provider = Provider(
    base_url="https://models.github.ai/inference",
    api_key=os.environ["GITHUB_TOKEN"],
    model="<publisher>/<model-name>",
)
```

The token needs permission to read models. See the
[GitHub Models quick start](https://docs.github.com/en/github-models/quickstart).

## Together AI

```python
provider = Provider(
    base_url="https://api.together.ai/v1",
    api_key=os.environ["TOGETHER_API_KEY"],
    model="<provider>/<model-name>",
)
```

See [Together AI OpenAI compatibility](https://docs.together.ai/docs/inference/openai-compatibility).

## Groq

```python
provider = Provider(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
    model="<model-id>",
)
```

See [Groq OpenAI compatibility](https://console.groq.com/docs/openai).

## Anthropic

Anthropic's Messages API is not the OpenAI chat-completions API. For live
requests, use an OpenAI-compatible gateway or write an `LLMProvider` adapter.

For offline fan-out work, ExecutionKit has a separate native integration. See
[Anthropic Message Batches](../integrations/message-batches.md).

## Azure OpenAI

The native Azure OpenAI REST API uses deployment-specific URLs, an
`api-version` query parameter, and authentication shapes that the default
`Provider` does not construct. Use an OpenAI-compatible gateway or implement a
custom `LLMProvider` for the native API.

## Provider options

| Parameter | Default | Meaning |
|---|---:|---|
| `base_url` | required | URL before `/chat/completions`. Must use `http` or `https`. |
| `model` | required | Model ID sent in every request. |
| `api_key` | `""` | Bearer token. An empty value omits the authorization header. |
| `default_temperature` | `0.7` | Used when a call does not supply `temperature`. |
| `default_max_tokens` | `4096` | Used when a call does not supply `max_tokens`. |
| `timeout` | `120.0` | Per-request timeout in seconds. |

Pattern-level `temperature` and `max_tokens` values override the provider
defaults.

## Connection lifecycle

```python
async with Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model=os.environ["OPENAI_MODEL"],
) as provider:
    result = await provider.complete([{"role": "user", "content": "Hello"}])
```

When `httpx` is installed, `Provider` owns an `httpx.AsyncClient`. Leave the
context or call `await provider.aclose()` to close it.

## Custom provider

Any object with the `LLMProvider.complete()` signature can be passed to a
pattern:

```python
from collections.abc import Sequence
from types import MappingProxyType
from typing import Any

from executionkit import LLMResponse


class MyProvider:
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        # Call the provider and translate its response here.
        return LLMResponse(
            content="translated response",
            usage=MappingProxyType(
                {"input_tokens": 10, "output_tokens": 3}
            ),
        )
```

For `react_loop()`, the adapter must also set `supports_tools = True` and
return `ToolCall` objects. Set the flag only when the adapter can send tool
schemas and parse tool calls correctly.

For streaming, implement the separate `StreamingProvider.stream()` protocol.
Read [Providers and responses](../api/adapters.md) for the exact interfaces.

## Security

- Store keys outside source code.
- Use HTTPS for remote endpoints.
- Treat `LLMResponse.raw` as unredacted provider data.
- Apply an endpoint allowlist in the calling application when users can
  influence `base_url`.
- Do not assume an endpoint supports tools or streaming because it supports
  basic chat completions.
