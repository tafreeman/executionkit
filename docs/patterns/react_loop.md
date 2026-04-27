# react_loop

Execute a think-act-observe tool-calling loop.

::: executionkit.patterns.react_loop.react_loop

## Example

```python
from executionkit import react_loop, Tool, Provider

provider = Provider("https://api.openai.com/v1", api_key=KEY, model="gpt-4o-mini")

async def search(query: str) -> str:
    return f"Results for: {query}"

search_tool = Tool(
    name="search",
    description="Search the web for current information.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    execute=search,
)

result = await react_loop(provider, "What is the latest Python version?", tools=[search_tool])
print(result.value)                         # Final answer
print(result.metadata["rounds"])            # 2
print(result.metadata["tool_calls_made"])   # 1
```

## Metadata Keys

| Key | Type | Description |
|-----|------|-------------|
| `rounds` | `int` | Think-act-observe cycles completed |
| `tool_calls_made` | `int` | Total individual tool invocations |
| `truncated_responses` | `int` | LLM responses truncated due to `finish_reason=length` |
| `truncated_observations` | `int` | Tool results truncated due to `max_observation_chars` |
| `messages_trimmed` | `int` | Rounds where history was trimmed |
