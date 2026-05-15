<div align="center">

# ExecutionKit

**Composable LLM reasoning patterns.**
Consensus voting · Iterative refinement · ReAct tool loops · Structured JSON · Zero SDK lock-in.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CI](https://github.com/tafreeman/executionkit/actions/workflows/ci.yml/badge.svg)](https://github.com/tafreeman/executionkit/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/tafreeman/executionkit/branch/main/graph/badge.svg)](https://codecov.io/gh/tafreeman/executionkit)
[![Linting: ruff](https://img.shields.io/badge/linting-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-amber)](https://tafreeman.github.io/executionkit/)

</div>

---

ExecutionKit fills the gap between raw chat calls and full orchestration stacks — more power than one-off prompts, less weight than a framework. Provider-agnostic, zero runtime dependencies (stdlib only), `mypy --strict` clean.

📚 **Full documentation: [tafreeman.github.io/executionkit](https://tafreeman.github.io/executionkit/)**

## For Reviewers

ExecutionKit is the execution-primitive layer of a two-tier stack. The companion repo,
[agentic-runtimes](https://github.com/tafreeman/agentic-runtimes), handles orchestration
above it — ExecutionKit patterns run inside each agent step there.

| File | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Module map, dependency graph, error hierarchy, security notes |
| [`CONTRIBUTING.md` — Anti-Scope](CONTRIBUTING.md#anti-scope) | What the library does not do, and why |
| [`examples/`](examples/) | `OPENAI_API_KEY=sk-... python examples/quickstart_openai.py` |

See [`PORTFOLIO.md`](PORTFOLIO.md) for full context.

## Quick Start

```bash
pip install executionkit
```

```python
import asyncio
import os
from executionkit import Provider, consensus

async def main() -> None:
    async with Provider(
        "https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    ) as provider:
        result = await consensus(provider, "Classify this ticket: ...", num_samples=5)
        print(result.value, result.metadata["agreement_ratio"], result.cost)

asyncio.run(main())
```

See the [Quick Start guide](https://tafreeman.github.io/executionkit/getting-started/quickstart/) for a complete walkthrough.

## Patterns

| Pattern | What it does |
|---------|--------------|
| **[Consensus](https://tafreeman.github.io/executionkit/patterns/consensus/)** | Run *N* parallel calls, vote on the result, return the majority answer with confidence. |
| **[Iterative Refinement](https://tafreeman.github.io/executionkit/patterns/iterative-refinement/)** | Generate, score, refine. Bounded loop with a quality gate. |
| **[ReAct Tool Loop](https://tafreeman.github.io/executionkit/patterns/react-loop/)** | Think-act-observe loop with JSON-Schema-validated tool calls. |
| **[Structured Output](https://tafreeman.github.io/executionkit/patterns/structured/)** | Parse JSON responses with custom validators and automatic repair retries. |
| **[Pipe](https://tafreeman.github.io/executionkit/patterns/pipe/)** | Chain patterns end-to-end with a shared budget. |

## Why ExecutionKit

- **Provider-agnostic.** OpenAI, Ollama, vLLM, GitHub Models, Together, Groq, llama.cpp, and Azure via an OpenAI-compatible gateway.
- **Zero SDK lock-in.** Structural `LLMProvider` protocol — any conforming object works without inheritance.
- **Composable.** Patterns are async functions. Wrap them, chain them with `pipe()`, or drop them inside a larger orchestrator like [agentic-runtimes](https://github.com/tafreeman/agentic-runtimes).
- **Budget-aware.** TOCTOU-safe `max_cost` enforcement across parallel calls.
- **Secure-by-default.** API key masking, credential redaction in errors, JSON-Schema tool validation, prompt-injection-hardened default evaluator.

## Relationship to agentic-runtimes

ExecutionKit and [agentic-runtimes](https://github.com/tafreeman/agentic-runtimes) occupy different layers of the same stack:

| | ExecutionKit | agentic-runtimes |
|---|---|---|
| **Role** | Pattern library | Orchestration runtime |
| **Scope** | Single LLM call patterns with cost tracking | Multi-agent DAG workflows with tiered model routing |
| **Workflow authoring** | Python functions | Declarative YAML |
| **Dependencies** | Zero (stdlib only; `httpx` optional) | FastAPI, LangGraph, Pydantic, provider SDKs |
| **Use when** | You need a reasoning primitive — vote, refine, tool loop | You need to orchestrate many agents with scheduling, retries, and evaluation |

**agentic-runtimes uses ExecutionKit patterns internally** as the execution primitive for each agent step. Build atop agentic-runtimes for free; install ExecutionKit alone if you want the patterns without the orchestration overhead.

## Documentation

The canonical reference is the [docs site](https://tafreeman.github.io/executionkit/):

- [Installation](https://tafreeman.github.io/executionkit/getting-started/installation/)
- [Quick Start](https://tafreeman.github.io/executionkit/getting-started/quickstart/)
- [Provider Setup](https://tafreeman.github.io/executionkit/getting-started/providers/)
- [Patterns Overview](https://tafreeman.github.io/executionkit/patterns/)
- [Recipes](https://tafreeman.github.io/executionkit/recipes/composition/) — failover, cost-aware routing, pattern composition.
- [API Reference](https://tafreeman.github.io/executionkit/api/core/)

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format . --check
mypy --strict executionkit/
pytest --cov=executionkit --cov-fail-under=80
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full dev workflow.

## License

MIT — see [LICENSE](LICENSE).
