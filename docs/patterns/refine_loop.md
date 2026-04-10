# refine_loop

Iteratively improve an LLM response until it converges or hits the budget.

::: executionkit.patterns.refine_loop.refine_loop

## Example

```python
from executionkit import refine_loop, Provider

provider = Provider("https://api.openai.com/v1", api_key=KEY, model="gpt-4o-mini")

result = await refine_loop(
    provider,
    "Write a concise explanation of gradient descent.",
    target_score=0.85,
    max_iterations=4,
)

print(result.value)                        # Best response
print(result.score)                        # 0.88
print(result.metadata["iterations"])       # 2
print(result.metadata["converged"])        # True
```

## Custom Evaluator

Supply your own scoring function to replace the default LLM-based evaluator:

```python
async def my_evaluator(text: str, provider) -> float:
    # Return a score in [0.0, 1.0]
    return 0.9 if len(text) > 100 else 0.4

result = await refine_loop(provider, "Write something.", evaluator=my_evaluator)
```

## Metadata Keys

| Key | Type | Description |
|-----|------|-------------|
| `iterations` | `int` | Refinement iterations performed (0 = converged on first attempt) |
| `converged` | `bool` | Whether the loop converged before `max_iterations` |
| `score_history` | `list[float]` | Score at each iteration including initial generation |
