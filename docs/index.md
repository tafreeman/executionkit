# ExecutionKit

Composable LLM reasoning patterns with budget-aware execution.

ExecutionKit fills the gap between raw chat calls and full orchestration stacks — more
power than one-off prompts, less weight than a framework.

## Quick Example

```python
import os
from executionkit import consensus, Provider

provider = Provider("https://api.openai.com/v1", api_key=os.environ["OPENAI_API_KEY"], model="gpt-4o-mini")

result = await consensus(provider, "Classify this support ticket: ...", num_samples=5)
print(result)                                # The classification
print(result.cost)                           # TokenUsage(input_tokens=250, output_tokens=45, llm_calls=5)
print(result.metadata["agreement_ratio"])    # 0.8 = 4 of 5 agreed
```

Works with ANY OpenAI-compatible endpoint — zero config change:

```python
ollama   = Provider("http://localhost:11434/v1", model="llama3.2")
github   = Provider("https://models.inference.ai.azure.com", api_key=GITHUB_TOKEN, model="gpt-4o-mini")
together = Provider("https://api.together.xyz/v1", api_key=TOGETHER_KEY, model="meta-llama/Llama-3-70b")
groq     = Provider("https://api.groq.com/openai/v1", api_key=GROQ_KEY, model="llama-3.3-70b")
```

## Features

- **Composable reasoning patterns**: `consensus`, `refine_loop`, `react_loop`, `pipe`
- **Budget-aware execution** with per-call cost tracking
- **Any OpenAI-compatible endpoint** — zero config change
- **Zero runtime dependencies** (stdlib only; `httpx` optional for connection pooling)
- **Type-safe** with full `mypy --strict` support
- **Security**: prompt injection defense, API key masking, credential redaction in errors
