---
hide:
  - toc
description: Provider-agnostic Python library for composable LLM execution patterns. Zero runtime dependencies.
---

[← tafreeman](https://github.com/tafreeman){ .ek-back }

<div class="ek-hero" markdown>

[Python · stdlib only · v0.1.0]{ .ek-eyebrow }

# ExecutionKit

<p class="ek-tagline">Composable LLM reasoning patterns.</p>
<p class="ek-subtagline">Consensus voting · Iterative refinement · ReAct tool loops · Structured JSON · Zero SDK lock-in.</p>

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

<div class="ek-card" markdown>
### [Structured Output](patterns/structured.md)
Request JSON, parse it, validate it, and repair malformed responses with bounded retries.
</div>

</div>

## Why ExecutionKit

<div class="ek-why" markdown>

<div class="ek-why-item" markdown>
#### Provider-agnostic
Works with any OpenAI-compatible endpoint: OpenAI, Anthropic via proxy, Ollama, vLLM, GitHub Models, local llama.cpp, and Azure via an OpenAI-compatible gateway.
</div>

<div class="ek-why-item" markdown>
#### Zero SDK lock-in
One adapter interface. Swap providers per pattern, per call, or via env var. The `LLMProvider` protocol is structural — any conforming object works.
</div>

<div class="ek-why-item" markdown>
#### Composable
Patterns are async functions. Wrap them, chain them with `pipe()`, or drop them inside a larger orchestrator like [agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform).
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

`pip install git+https://github.com/tafreeman/executionkit.git` — zero runtime dependencies (stdlib only). Add `[httpx]` for connection pooling.

## Relationship to agentic-runtime-platform

ExecutionKit is **the pattern library**. [agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform) is **the orchestration runtime**.

Use **ExecutionKit alone** for adding reasoning patterns to an existing app — a single async call drops into any service.

Use **agentic-runtime-platform** when you need DAG-based multi-step workflows with tiered model routing and evaluation gating.

The two are designed to compose: agentic-runtime-platform calls ExecutionKit patterns inside its workflow steps. ExecutionKit owns the *how* of one reasoning step; agentic-runtime-platform owns the *when* and *next* across many.

| Need | Reach for |
|------|-----------|
| One-shot voting / refinement / structured extraction / tool loop in your app | ExecutionKit |
| Multi-step DAG with state, retries, and gating | agentic-runtime-platform |
| Cost ceiling per request | ExecutionKit `max_cost=` |
| Cost ceiling per workflow with per-step budgets | agentic-runtime-platform + ExecutionKit |
| Custom provider — Anthropic, vLLM, llama.cpp | ExecutionKit `LLMProvider` protocol |
| Per-step model routing (Haiku → Sonnet → Opus) | agentic-runtime-platform |

---

<small>License: [MIT](license.md) · [Changelog](changelog.md) · [Contributing](contributing.md)</small>
