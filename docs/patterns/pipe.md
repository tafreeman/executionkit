# pipe

Chain patterns together, threading each result's value as the next prompt.

::: executionkit.compose.pipe

## Example

```python
from executionkit import pipe, consensus, refine_loop, Provider

provider = Provider("https://api.openai.com/v1", api_key=KEY, model="gpt-4o-mini")

# Draft via consensus, then refine the winner
result = await pipe(
    provider,
    "Explain quantum entanglement in one paragraph.",
    patterns=[consensus, refine_loop],
)

print(result.value)   # Refined consensus winner
print(result.cost)    # Combined cost across both patterns
```

## Shared Budget

Pass a single `max_cost` budget shared across all chained patterns:

```python
from executionkit.types import TokenUsage

budget = TokenUsage(input_tokens=20_000, output_tokens=10_000, llm_calls=20)

result = await pipe(
    provider,
    "...",
    patterns=[consensus, refine_loop],
    max_cost=budget,
)
```

If the budget is exhausted mid-chain, `BudgetExhaustedError` is raised with the accumulated cost.
