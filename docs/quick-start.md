# Quick Start

## Installation

```bash
pip install executionkit
```

For high-throughput workloads with connection pooling:

```bash
pip install executionkit[httpx]
```

Requires Python 3.11+.

## Provider Setup

```python
import os
from executionkit import Provider

provider = Provider(
    base_url="https://api.openai.com/v1",
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o-mini",
)
```

## Consensus

Run parallel samples and pick the majority answer:

```python
from executionkit import consensus

result = await consensus(provider, "What is the capital of France?", num_samples=3)
print(result)                                     # Paris
print(result.metadata["agreement_ratio"])         # 1.0
print(result.cost)                                # TokenUsage(...)
```

## Refine Loop

Iteratively improve a response until it meets a quality target:

```python
from executionkit import refine_loop

result = await refine_loop(
    provider,
    "Write a one-paragraph summary of the Turing test.",
    target_score=0.85,
    max_iterations=4,
)
print(result)                                     # Best response found
print(result.score)                               # 0.91
print(result.metadata["iterations"])              # 2
```

## React Loop (Tool Calling)

```python
from executionkit import react_loop, Tool

async def _calculator(expression: str) -> str:
    ...  # use a safe AST-based evaluator

calc_tool = Tool(
    name="calculator",
    description="Evaluate a math expression and return the result.",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
    execute=_calculator,
)

result = await react_loop(provider, "What is 17 * 83?", tools=[calc_tool])
print(result)                                     # 1411
print(result.metadata["tool_calls_made"])         # 1
```

## Budget Control

All patterns accept a `max_cost` budget:

```python
from executionkit.types import TokenUsage

budget = TokenUsage(input_tokens=10_000, output_tokens=5_000, llm_calls=10)
result = await consensus(provider, "...", max_cost=budget)
```

If the budget is exceeded, `BudgetExhaustedError` is raised with the accumulated cost snapshot.
