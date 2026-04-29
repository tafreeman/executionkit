# ExecutionKit

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Coverage: 83%](https://img.shields.io/badge/coverage-83%25-brightgreen)](pyproject.toml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-amber)](https://tafreeman.github.io/executionkit/)

**Composable LLM reasoning patterns.**
Consensus voting · Iterative refinement · ReAct tool loops · Zero SDK lock-in.

ExecutionKit fills the gap between raw chat calls and full orchestration stacks — more power than one-off prompts, less weight than a framework. Provider-agnostic, zero runtime dependencies (stdlib only), `mypy --strict` clean.

📚 **Full documentation: [tafreeman.github.io/executionkit](https://tafreeman.github.io/executionkit/)**

## Quick Start

```bash
pip install executionkit
```

```python
from executionkit import Provider, consensus

provider = Provider("https://api.openai.com/v1", api_key=KEY, model="gpt-4o-mini")
result  = await consensus(provider, "Classify this ticket: ...", num_samples=5)
print(result.value, result.metadata["agreement_ratio"], result.cost)
```

See the [Quick Start guide](https://tafreeman.github.io/executionkit/getting-started/quickstart/) for a complete walkthrough.

## Patterns

| Pattern | What it does |
|---------|--------------|
| **[Consensus](https://tafreeman.github.io/executionkit/patterns/consensus/)** | Run *N* parallel calls, vote on the result, return the majority answer with confidence. |
| **[Iterative Refinement](https://tafreeman.github.io/executionkit/patterns/iterative-refinement/)** | Generate, score, refine. Bounded loop with a quality gate. |
| **[ReAct Tool Loop](https://tafreeman.github.io/executionkit/patterns/react-loop/)** | Think-act-observe loop with JSON-Schema-validated tool calls. |
| **[Pipe](https://tafreeman.github.io/executionkit/patterns/pipe/)** | Chain patterns end-to-end with a shared budget. |

## Why ExecutionKit

- **Provider-agnostic.** OpenAI, Azure, Ollama, vLLM, GitHub Models, Together, Groq, llama.cpp — anything OpenAI-compatible.
- **Zero SDK lock-in.** Structural `LLMProvider` protocol — any conforming object works without inheritance.
- **Composable.** Patterns are async functions. Wrap them, chain them with `pipe()`, or drop them inside a larger orchestrator like [agentic-runtimes](https://github.com/tafreeman/agentic-runtimes).
- **Budget-aware.** TOCTOU-safe `max_cost` enforcement across parallel calls.
- **Secure-by-default.** API key masking, credential redaction in errors, JSON-Schema tool validation, prompt-injection-hardened default evaluator.

## Documentation

The canonical reference is the [docs site](https://tafreeman.github.io/executionkit/):

- [Installation](https://tafreeman.github.io/executionkit/getting-started/installation/)
- [Quick Start](https://tafreeman.github.io/executionkit/getting-started/quickstart/)
- [Provider Setup](https://tafreeman.github.io/executionkit/getting-started/providers/)
- [Patterns Overview](https://tafreeman.github.io/executionkit/patterns/)
- [Recipes](https://tafreeman.github.io/executionkit/recipes/composition/) — failover, cost-aware routing, pattern composition.
- [API Reference](https://tafreeman.github.io/executionkit/api/core/)

## Relationship to agentic-runtimes

ExecutionKit is **the pattern library**. [agentic-runtimes](https://github.com/tafreeman/agentic-runtimes) is **the orchestration runtime**. Use ExecutionKit alone for adding reasoning patterns to an existing app; reach for agentic-runtimes when you need DAG-based multi-step workflows. The two compose: agentic-runtimes calls ExecutionKit patterns inside its workflow steps.

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
