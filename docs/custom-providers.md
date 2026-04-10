# Custom Providers

ExecutionKit works with any OpenAI-compatible endpoint. No config changes needed.

## Built-in Endpoints

```python
from executionkit import Provider

# OpenAI
provider = Provider("https://api.openai.com/v1", api_key=OPENAI_KEY, model="gpt-4o-mini")

# Ollama (local — no API key)
provider = Provider("http://localhost:11434/v1", model="llama3.2")

# GitHub Models
provider = Provider("https://models.inference.ai.azure.com", api_key=GITHUB_TOKEN, model="gpt-4o-mini")

# Together AI
provider = Provider("https://api.together.xyz/v1", api_key=TOGETHER_KEY, model="meta-llama/Llama-3-70b")

# Groq
provider = Provider("https://api.groq.com/openai/v1", api_key=GROQ_KEY, model="llama-3.3-70b")
```

## Custom Provider Protocol

For backends that don't speak the OpenAI format, implement the `LLMProvider` protocol:

```python
from executionkit.provider import LLMProvider, LLMResponse
from collections.abc import Sequence
from typing import Any

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
        # Call your backend here
        ...
        return LLMResponse(content="response text")
```

No inheritance required — structural typing (PEP 544) is used throughout.

## Tool-Calling Provider

For `react_loop`, your provider must also expose `supports_tools = True`:

```python
class MyToolProvider:
    supports_tools = True  # required for ToolCallingProvider protocol

    async def complete(self, messages, *, tools=None, **kwargs):
        ...
```

## Context Manager

`Provider` supports `async with` for clean resource management:

```python
async with Provider("https://api.openai.com/v1", api_key=KEY, model="gpt-4o") as provider:
    result = await consensus(provider, "...")
```
