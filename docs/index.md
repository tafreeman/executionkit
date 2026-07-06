---
title: ExecutionKit
description: Provider-agnostic LLM execution primitives — consensus, ReAct, budget-aware calls. Zero runtime dependencies.
hide:
  - toc
---

<div class="console-hero" markdown="1">
<div class="hero-inner" markdown="1">

<div class="hero-meta">
  <span class="hero-eyebrow">L1 · primitives · LLM execution</span>
  <span class="status-tag">status: active</span>
</div>

# ExecutionKit

<p class="hero-sub">Provider-agnostic LLM execution primitives — consensus, ReAct, budget-aware calls. Zero runtime dependencies. Consensus voting, iterative refinement, ReAct tool loops, structured output, and pipe composition, plus lightweight routing, workflow, planning, and approval-gate primitives — all `mypy --strict` clean, all stdlib only.</p>

<div class="hero-actions" markdown>
[Get started](getting-started/quickstart.md){ .md-button .md-button--primary }
[View source](https://github.com/tafreeman/executionkit){ .md-button }
</div>

<div class="term">
  <span class="term-prompt">$</span>
  <span class="term-cmd">pip install executionkit</span>
  <span class="term-comment"># zero runtime dependencies — stdlib only</span>
</div>

</div>
</div>

<div class="trusted-stack" markdown>
<span>Python 3.11+</span>
<span>Zero runtime deps</span>
<span>mypy --strict</span>
<span>OpenAI-compatible</span>
<span>httpx (optional)</span>
<span>MIT license</span>
</div>

[part of the Console portfolio](https://tafreeman.github.io/tafreeman/){ .link-forward }

<p class="section-kicker">get running</p>

## Quick start

No framework, no adapter matrix — one `Provider`, five reasoning patterns.

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
            "What is the capital of France?",
            num_samples=3,
        )
        print(result.value)                          # Paris
        print(result.metadata["agreement_ratio"])    # 1.0
        print(result.cost)                           # TokenUsage(input_tokens=..., output_tokens=..., llm_calls=3)

asyncio.run(main())
```

Swap in Ollama, vLLM, Groq, Together, GitHub Models, or Azure via an OpenAI-compatible gateway — same `Provider`, same patterns.

[Full walkthrough](getting-started/quickstart.md){ .link-forward }

---

<p class="section-kicker">patterns</p>

## Five composable reasoning patterns

<div class="feature-grid" markdown>

<div class="feature-card" markdown>
<div class="fc-icon"><svg fill="currentColor" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><polygon points="13 24 4 15 5.414 13.586 13 21.171 26.586 7.586 28 9 13 24"></polygon></svg></div>
<h3 class="fc-title">Consensus</h3>
<p class="fc-body">Run <em>N</em> independent calls, vote on the result, return the majority answer with an agreement-ratio confidence score.</p>
[Consensus](patterns/consensus.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<div class="fc-icon"><svg fill="currentColor" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M27,16.76c0-.25,0-.5,0-.76s0-.51,0-.77l1.92-1.68A2,2,0,0,0,29.3,11L26.94,7a2,2,0,0,0-1.73-1,2,2,0,0,0-.64.1l-2.43.82a11.35,11.35,0,0,0-1.31-.75l-.51-2.52a2,2,0,0,0-2-1.61H13.64a2,2,0,0,0-2,1.61l-.51,2.52a11.48,11.48,0,0,0-1.32.75L7.43,6.06A2,2,0,0,0,6.79,6,2,2,0,0,0,5.06,7L2.7,11a2,2,0,0,0,.41,2.51L5,15.24c0,.25,0,.5,0,.76s0,.51,0,.77L3.11,18.45A2,2,0,0,0,2.7,21L5.06,25a2,2,0,0,0,1.73,1,2,2,0,0,0,.64-.1l2.43-.82a11.35,11.35,0,0,0,1.31.75l.51,2.52a2,2,0,0,0,2,1.61h4.72a2,2,0,0,0,2-1.61l.51-2.52a11.48,11.48,0,0,0,1.32-.75l2.42.82a2,2,0,0,0,.64.1,2,2,0,0,0,1.73-1L29.3,21a2,2,0,0,0-.41-2.51ZM25.21,24l-3.43-1.16a8.86,8.86,0,0,1-2.71,1.57L18.36,28H13.64l-.71-3.55a9.36,9.36,0,0,1-2.7-1.57L6.79,24,4.43,20l2.72-2.4a8.9,8.9,0,0,1,0-3.13L4.43,12,6.79,8l3.43,1.16a8.86,8.86,0,0,1,2.71-1.57L13.64,4h4.72l.71,3.55a9.36,9.36,0,0,1,2.7,1.57L25.21,8,27.57,12l-2.72,2.4a8.9,8.9,0,0,1,0,3.13L27.57,20Z"></path></svg></div>
<h3 class="fc-title">Iterative refinement</h3>
<p class="fc-body">Generate, critique, regenerate — a bounded loop with a quality gate. Stops early once <code>target_score</code> is reached.</p>
[Iterative refinement](patterns/iterative-refinement.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<div class="fc-icon"><svg fill="currentColor" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M26,4H6A2,2,0,0,0,4,6V26a2,2,0,0,0,2,2H26a2,2,0,0,0,2-2V6A2,2,0,0,0,26,4Zm0,2v4H6V6ZM6,26V12H26V26Z"></path><polygon points="10.76 16.18 13.58 19.01 10.76 21.84 12.17 23.25 16.41 19.01 12.17 14.77 10.76 16.18"></polygon></svg></div>
<h3 class="fc-title">ReAct tool loop</h3>
<p class="fc-body">Think → act → observe with a hard model→tool boundary: schema-validated arguments, per-call timeouts, and bounded fan-out on every axis.</p>
[ReAct tool loop](patterns/react-loop.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<div class="fc-icon"><svg fill="currentColor" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M27,22.14V17a2,2,0,0,0-2-2H17V9.86a4,4,0,1,0-2,0V15H7a2,2,0,0,0-2,2v5.14a4,4,0,1,0,2,0V17H25v5.14a4,4,0,1,0,2,0ZM8,26a2,2,0,1,1-2-2A2,2,0,0,1,8,26ZM14,6a2,2,0,1,1,2,2A2,2,0,0,1,14,6ZM26,28a2,2,0,1,1,2-2A2,2,0,0,1,26,28Z"></path></svg></div>
<h3 class="fc-title">Structured output</h3>
<p class="fc-body">Request JSON, parse it, validate it against a custom validator, and repair malformed responses with bounded retries.</p>
[Structured output](patterns/structured.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<div class="fc-icon"><svg fill="currentColor" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="m20,6c0,1.8587,1.2795,3.4109,3,3.858v4.142c0,1.6543-1.3457,3-3,3h-8c-1.1299,0-2.1617.391-3,1.0256v-8.1676c1.7203-.4471,3-1.9993,3-3.858,0-2.2061-1.7944-4-4-4s-4,1.7939-4,4c0,1.8587,1.2797,3.4108,3,3.858v12.142s0,.142,0,.142c-1.7203.4473-3,1.9997-3,3.858,0,2.2056,1.7944,4,4,4s4-1.7944,4-4c0-1.8583-1.2797-3.4107-3-3.858v-.142c0-1.6543,1.3457-3,3-3h8c2.7568,0,5-2.2432,5-5v-4.142c1.7205-.4471,3-1.9993,3-3.858,0-2.2061-1.7939-4-4-4s-4,1.7939-4,4Zm-14,0c0-1.1025.897-2,2-2s2,.8975,2,2c0,1.1025-.897,2-2,2s-2-.8975-2-2Zm4,20c0,1.103-.897,2-2,2s-2-.897-2-2,.897-2,2-2,2,.897,2,2ZM26,6c0,1.1025-.8975,2-2,2s-2-.8975-2-2c0-1.1025.8975-2,2-2s2,.8975,2,2Z"></path></svg></div>
<h3 class="fc-title">Pipe composition</h3>
<p class="fc-body">Chain patterns end-to-end — thread one result into the next prompt with a shared budget tracked across every step.</p>
[Pipe composition](patterns/pipe.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<div class="fc-icon"><svg fill="currentColor" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M30,30H22V22h8Zm-6-2h4V24H24Z"></path><path d="M20,27H8A6,6,0,0,1,8,15h2v2H8a4,4,0,0,0,0,8H20Z"></path><path d="M20,20H12V12h8Zm-6-2h4V14H14Z"></path><path d="M24,17H22V15h2a4,4,0,0,0,0-8H12V5H24a6,6,0,0,1,0,12Z"></path><path d="M10,10H2V2h8ZM4,8H8V4H4Z"></path></svg></div>
<h3 class="fc-title">Map-reduce</h3>
<p class="fc-body">Fan a prompt across independent inputs with <code>gather_strict</code>, then reduce with a single call — bounded concurrency throughout.</p>
[Patterns overview](patterns/index.md){ .fc-link }
</div>

</div>

---

<p class="section-kicker">why executionkit</p>

## The gap between raw chat calls and full orchestration

<div class="feature-grid" markdown>

<div class="feature-card" markdown>
<h3 class="fc-title">Provider-agnostic</h3>
<p class="fc-body">Works with any OpenAI-compatible endpoint: OpenAI, Ollama, vLLM, Groq, Together, GitHub Models, llama.cpp, and Azure via an OpenAI-compatible gateway. The <code>LLMProvider</code> protocol is structural — any conforming object works without inheritance.</p>
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">Zero SDK lock-in</h3>
<p class="fc-body">One adapter interface. Swap providers per pattern, per call, or via env var — no dependency conflict, no framework to pin.</p>
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">Budget-aware</h3>
<p class="fc-body">TOCTOU-safe <code>max_cost</code> enforcement across parallel calls. <code>llm_calls</code> counts every dispatched wire attempt, including failed retries.</p>
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">Resilient by construction</h3>
<p class="fc-body">A retryable allowlist plus a token-bucket rate limiter give circuit-breaker / bulkhead-style behavior: full-jitter backoff, immediate cooldown on a 429's <code>retry_after</code>, and fail-fast on non-retryable errors.</p>
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">Secure by default</h3>
<p class="fc-body">API key masking, broad credential redaction in error messages, JSON-Schema tool-argument validation, and a prompt-injection-hardened default evaluator.</p>
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">Eval-aware</h3>
<p class="fc-body">A deterministic golden suite and a curated model-failure corpus assert output <em>correctness</em> — not just coverage — in every CI run, with an opt-in live-provider regression tier.</p>
</div>

</div>

---

<p class="section-kicker">metrics</p>

## By the numbers

<div class="stat-strip" markdown>
<div class="stat-item">
  <div class="stat-value">0</div>
  <div class="stat-label">Runtime dependencies</div>
</div>
<div class="stat-item">
  <div class="stat-value">5</div>
  <div class="stat-label">Reasoning patterns</div>
</div>
<div class="stat-item">
  <div class="stat-value">80%</div>
  <div class="stat-label">Coverage gate, CI-enforced</div>
</div>
<div class="stat-item">
  <div class="stat-value">15</div>
  <div class="stat-label">ADRs</div>
</div>
<div class="stat-item">
  <div class="stat-value">8</div>
  <div class="stat-label">OpenAI-compatible providers</div>
</div>
<div class="stat-item">
  <div class="stat-value">3.11+</div>
  <div class="stat-label">Python, strict mypy</div>
</div>
</div>

---

<p class="section-kicker">engineering practice</p>

## Built for platform teams

<div class="feature-grid practice-grid" markdown>

<div class="feature-card" markdown>
<h3 class="fc-title">A written decision record</h3>
<p class="fc-body">15 architecture decision records capture context, alternatives, and consequences for every consequential choice — structural protocols over ABCs, flat package layout, zero runtime dependencies, the tool-execution sandbox contract.</p>
[ADR index](adr/README.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">Correctness gated in CI</h3>
<p class="fc-body">An 80% coverage gate, ruff and <code>mypy --strict</code> on the full package, and a Bandit SAST job — plus a deterministic golden eval suite that checks output correctness, not just line coverage.</p>
[Contributing](contributing.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">A hard tool-execution boundary</h3>
<p class="fc-body">The model→tool edge is schema-validated, per-call timeout-bounded, and fan-out-capped on every axis — surplus tool calls are rejected with an observation, never executed.</p>
[Tool sandbox ADR](adr/015-react-loop-tool-sandbox.md){ .fc-link }
</div>

<div class="feature-card" markdown>
<h3 class="fc-title">Honestly scoped</h3>
<p class="fc-body">A maintained Anti-Scope section states plainly what a pattern library does not do — no RAG, no multi-agent handoff, no framework. <code>CONTRIBUTING.md</code> draws the line and holds it.</p>
[Contributing &amp; anti-scope](contributing.md){ .fc-link }
</div>

</div>

---

<p class="section-kicker">documentation</p>

## Where to go next

<div class="doc-grid" markdown>

<div class="doc-card" markdown>
<h3 class="dc-title">Getting started</h3>

- [Installation](getting-started/installation.md) — pip install, extras, Python version support
- [Quick start](getting-started/quickstart.md) — five lines from install to a consensus call
- [Provider setup](getting-started/providers.md) — OpenAI, Ollama, Groq, Together, GitHub Models, Azure
</div>

<div class="doc-card" markdown>
<h3 class="dc-title">Patterns</h3>

- [Overview](patterns/index.md) — pick the right pattern for your problem
- [Consensus](patterns/consensus.md) — vote across independent samples
- [ReAct tool loop](patterns/react-loop.md) — think, act, observe
- [Structured output](patterns/structured.md) — JSON with repair retries
</div>

<div class="doc-card" markdown>
<h3 class="dc-title">Recipes</h3>

- [Multi-provider failover](recipes/failover.md) — resilient provider chains
- [Cost-aware routing](recipes/cost-routing.md) — route on budget and tier
- [Conversational assistant](recipes/assistant.md) — a stateful chat loop
- [Combining patterns](recipes/composition.md) — compose with <code>pipe()</code>
</div>

<div class="doc-card" markdown>
<h3 class="dc-title">Reference</h3>

- [Architecture](architecture.md) — module map, dependency graph, error hierarchy
- [API reference](api/core.md) — core, adapters, configuration
- [ADR index](adr/README.md) — every architecture decision, dated and rationalized
- [Security](security.md) — threat model and hardening notes
</div>

</div>

<div class="cta-card" markdown>
### Need orchestration on top?

ExecutionKit is the execution-primitive layer. For persistent, declarative, multi-agent workflows with tiered model routing and fleet-level evaluation gating, [agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform) layers over it — the runtime calls ExecutionKit patterns inside every agent step.

<div class="hero-actions" markdown>
[Read the architecture](architecture.md){ .md-button .md-button--primary }
[Open agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform){ .md-button }
</div>
</div>
