# Provider Setup

`Provider` speaks the OpenAI-compatible `/chat/completions` JSON format using bearer-token authentication. Anything that endpoint shape supports works without changes — swap `base_url`, `api_key`, and `model`.

## OpenAI

```python
import os
from executionkit import Provider

provider = Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o-mini",
)
```

## Anthropic (via OpenAI-compatible proxy)

Anthropic does not natively serve the OpenAI format. Use a proxy such as [LiteLLM](https://github.com/BerriAI/litellm) or run Claude through a compatible gateway:

```python
provider = Provider(
    base_url="http://localhost:4000",                  # LiteLLM proxy
    api_key=os.environ["ANTHROPIC_API_KEY"],
    model="claude-3-5-haiku-latest",
)
```

## Azure OpenAI through a compatible gateway

Azure OpenAI's native REST API uses an `api-version` query parameter and `api-key` header shape that the default `Provider` does not construct directly. Use Azure through an OpenAI-compatible gateway or proxy that exposes `/v1/chat/completions` with bearer-token authentication.

```python
provider = Provider(
    base_url="https://YOUR-GATEWAY.example.com/v1",
    api_key=os.environ["AZURE_GATEWAY_API_KEY"],
    model="YOUR-DEPLOYMENT",
)
```

## Ollama (local)

```python
provider = Provider(
    base_url="http://localhost:11434/v1",
    model="llama3.2",
    # No api_key needed for local Ollama
)
```

## vLLM (self-hosted)

```python
provider = Provider(
    base_url="http://your-vllm-host:8000/v1",
    model="meta-llama/Llama-3.1-8B-Instruct",
)
```

## llama.cpp server

```python
provider = Provider(
    base_url="http://localhost:8080/v1",
    model="local",
)
```

## GitHub Models

```python
provider = Provider(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],
    model="gpt-4o-mini",
)
```

## Together AI

```python
provider = Provider(
    base_url="https://api.together.xyz/v1",
    api_key=os.environ["TOGETHER_API_KEY"],
    model="meta-llama/Llama-3-70b-chat-hf",
)
```

## Groq

```python
provider = Provider(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ["GROQ_API_KEY"],
    model="llama-3.3-70b-versatile",
)
```

## Optional Provider parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `default_temperature` | `0.7` | Temperature used when not overridden per call |
| `default_max_tokens` | `4096` | Max tokens when not overridden per call |
| `timeout` | `120.0` | HTTP request timeout in seconds |

Per-call overrides on `consensus`, `refine_loop`, `react_loop`, and `structured` always win over the provider defaults.

## Lifecycle

`Provider` supports the async context manager protocol for clean resource management:

```python
async with Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o-mini",
) as provider:
    result = await consensus(provider, "...")
```

Calling `await provider.aclose()` manually is equivalent.

## Custom providers

Anything matching the `LLMProvider` structural protocol works — no inheritance required:

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
        # Call your API here
        return LLMResponse(content="Hello", usage={})
```

For tool-calling support (`react_loop`), set `supports_tools = True` on the class. See [API → Adapters](../api/adapters.md) for the full protocol.

## Security notes

- `Provider.__repr__` masks `api_key` as `***` regardless of length or prefix — never leaks in logs or tracebacks.
- HTTP error messages are scanned for credential-shaped substrings (`sk-...`, `bearer ...`, `token=...`, etc.) and redacted to `[REDACTED]` before being raised.
- All examples here read credentials from environment variables. Never commit keys.
