# structured

Request structured JSON output with optional repair and validation.

::: executionkit.patterns.structured.structured

## Example

```python
from executionkit import structured, Provider

provider = Provider("https://api.openai.com/v1", api_key=KEY, model="gpt-4o-mini")

result = await structured(
    provider,
    "Return a JSON object with keys 'summary' and 'confidence'.",
)

print(result.value["summary"])
print(result.metadata["parse_attempts"])
```

## Validator example

```python
def validator(value):
    if value.get("confidence", 0) < 0.8:
        return "confidence must be at least 0.8"
    return None

result = await structured(provider, "Return a confident classification.", validator=validator)
```
