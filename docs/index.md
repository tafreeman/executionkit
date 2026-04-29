---
hide:
  - toc
---

<div class="ek-hero" markdown>

# ExecutionKit

<p class="ek-tagline">Composable LLM reasoning patterns.</p>
<p class="ek-subtagline">Consensus voting · Iterative refinement · ReAct tool loops · Zero SDK lock-in.</p>

[Quick Start](getting-started/quickstart.md){ .ek-cta .ek-cta-primary }
[Patterns](patterns/index.md){ .ek-cta .ek-cta-secondary }
[GitHub →](https://github.com/tafreeman/executionkit){ .ek-cta .ek-cta-secondary }

</div>

## Patterns

<div class="ek-card-grid" markdown>

<div class="ek-card" markdown>
### [Consensus](patterns/consensus.md)
Run *N* independent calls, score agreement, return the majority answer with confidence. Reduces hallucination on factual questions.
</div>

<div class="ek-card" markdown>
### [Iterative Refinement](patterns/iterative-refinement.md)
Generate, critique, regenerate. Bounded loop with a quality gate. Used in code review and writing tasks.
</div>

<div class="ek-card" markdown>
### [ReAct Tool Loop](patterns/react-loop.md)
Reasoning + acting + observing. Standard tool-use loop with bounded iterations and graceful timeout.
</div>

<div class="ek-card" markdown>
### [Pipe Composition](patterns/pipe.md)
Chain patterns end-to-end. Thread one result into the next prompt with a shared budget across all steps.
</div>

</div>

## Why ExecutionKit

<div class="ek-why" markdown>

<div class="ek-why-item" markdown>
#### Provider-agnostic
Works with any OpenAI-compatible endpoint: OpenAI, Anthropic via proxy, Azure, Ollama, vLLM, GitHub Models, local llama.cpp.
</div>

<div class="ek-why-item" markdown>
#### Zero SDK lock-in
One adapter interface. Swap providers per pattern, per call, or via env var. The `LLMProvider` protocol is structural — any conforming object works.
</div>

<div class="ek-why-item" markdown>
#### Composable
Patterns are async functions. Wrap them, chain them with `pipe()`, or drop them inside a larger orchestrator like agentic-runtimes.
</div>

</div>

## Quick Start

```python
import asyncio
import os
from executionkit import Provider, consensus

async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    ) as provider:
        result = await consensus(
            provider,
            "Classify this support ticket as 'billing', 'tech', or 'other': "
            "'My card was charged twice this month.'",
            num_samples=5,
        )
        print(result.value)                          # billing
        print(result.score)                          # 1.0
        print(result.metadata["agreement_ratio"])    # 1.0
        print(result.cost)                           # TokenUsage(input_tokens=..., output_tokens=..., llm_calls=5)

asyncio.run(main())
```

`pip install executionkit` — zero runtime dependencies (stdlib only). Add `[httpx]` for connection pooling.

## Relationship to agentic-runtimes

ExecutionKit is **the pattern library**. [agentic-runtimes](https://github.com/tafreeman/agentic-runtimes) is **the orchestration runtime**.

Use **ExecutionKit alone** for adding reasoning patterns to an existing app — a single async call drops into any service.

Use **agentic-runtimes** when you need DAG-based multi-step workflows with tiered model routing and evaluation gating.

The two are designed to compose: agentic-runtimes calls ExecutionKit patterns inside its workflow steps. ExecutionKit owns the *how* of one reasoning step; agentic-runtimes owns the *when* and *next* across many.

| Need | Reach for |
|------|-----------|
| One-shot voting / refinement / tool loop in your app | ExecutionKit |
| Multi-step DAG with state, retries, and gating | agentic-runtimes |
| Cost ceiling per request | ExecutionKit `max_cost=` |
| Cost ceiling per workflow with per-step budgets | agentic-runtimes + ExecutionKit |
| Custom provider — Anthropic, vLLM, llama.cpp | ExecutionKit `LLMProvider` protocol |
| Per-step model routing (Haiku → Sonnet → Opus) | agentic-runtimes |

---

<small>License: [MIT](license.md) · [Changelog](changelog.md) · [Contributing](contributing.md)</small>
