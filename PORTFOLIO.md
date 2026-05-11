# PORTFOLIO.md

## What This Repo Is

ExecutionKit is a Python library of composable LLM reasoning patterns. It sits between
raw chat calls and full orchestration stacks — no SDK dependencies, no framework overhead.

It does not include dashboards, multi-agent routing, stateful graphs, or native provider
adapters. See [CONTRIBUTING.md — Anti-Scope](CONTRIBUTING.md#anti-scope) for the reasoning
behind those boundaries.

Three patterns ship: `consensus` (parallel voting), `refine_loop` (iterative improvement),
`react_loop` (tool calling). They compose via `pipe()`, accept any `LLMProvider`-conforming
object without inheritance, and enforce token/call budgets across parallel calls.

## Where This Sits in the Stack

```
agentic-runtimes          ← multi-agent DAG orchestration, YAML workflows, FastAPI runtime
  └── ExecutionKit (this)
        └── LLM provider  ← any OpenAI-compatible endpoint
```

[agentic-runtimes](https://github.com/tafreeman/agentic-runtimes) uses ExecutionKit
patterns as the execution primitive for each agent step. ExecutionKit has zero runtime
dependencies; agentic-runtimes depends on FastAPI, LangGraph, and provider SDKs.

## Where to Start

| File | Contents |
|------|----------|
| [`docs/architecture.md`](docs/architecture.md) | Module map, dependency graph, data flow, error hierarchy, security notes, extension points |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Dev setup, coding rules, commit convention, PR process, anti-scope list |
| [`executionkit/provider.py`](executionkit/provider.py) | `LLMProvider` protocol, `Provider` class, HTTP error classification |
| [`executionkit/cost.py`](executionkit/cost.py) | `CostTracker` — two-phase call accounting |
| [`examples/`](examples/) | Runnable scripts; set `OPENAI_API_KEY` or point at a local Ollama instance |

## Design Decisions

ADRs are in [`docs/adr/`](docs/adr/) (being written — Sprint 2). Short version:

**Structural protocols over abstract base classes.** Any object with a matching `complete`
signature satisfies `LLMProvider` (PEP 544) without inheritance. Background:
[`docs/planning/FINAL_VERDICT.md`](docs/planning/FINAL_VERDICT.md).

**Single `Provider` class over a native adapter matrix.** Most providers support the
OpenAI-compatible wire format. A native adapter per provider adds maintenance surface and
forces SDK dependencies. [`dev/BUILD_SPEC.md`](dev/BUILD_SPEC.md) has the full reasoning.

**Flat package layout over `src/`.** For a library this size, `src/` adds no benefit and
breaks `python -c "import executionkit"` without an install step. Documented in
[`docs/architecture.md`](docs/architecture.md).

## CI and Tooling

- `mypy --strict` on all 20 source modules; `py.typed` (PEP 561)
- ruff rules: E/F/W/I/N/UP/S/B/A/C4/SIM/TCH/RUF
- Bandit SAST in CI; `detect-private-key` pre-commit hook
- 387 tests; 85% coverage; `MockProvider` in all unit tests (no live API calls)
- Matrix CI: Python 3.11 / 3.12 / 3.13, Ubuntu + Windows
- Dependabot weekly on pip and GitHub Actions

## What Is Not Here

- **LLM eval harness** — planned Sprint 3; see [`dev/PORTFOLIO_BACKLOG.md`](dev/PORTFOLIO_BACKLOG.md)
- **OpenTelemetry tracing** — planned Sprint 3 as an optional hook
- **TypeScript / HTML** — planned Sprint 4
- **Federal deployment notes** — planned Sprint 3; the Ollama path supports air-gapped use
  but the deployment guidance isn't written yet
