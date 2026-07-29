<div align="center">

# ExecutionKit

**Async Python functions for repeatable LLM call patterns, tool loops, and small execution workflows.**

[![Python 3.11-3.13](https://img.shields.io/badge/python-3.11--3.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/executionkit)](https://pypi.org/project/executionkit/)
[![CI](https://github.com/tafreeman/executionkit/actions/workflows/ci.yml/badge.svg)](https://github.com/tafreeman/executionkit/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-MkDocs-amber)](https://tafreeman.github.io/executionkit/)

</div>

ExecutionKit sits between a raw chat-completions call and a workflow runtime. It
provides bounded functions for common call patterns, plus small helpers for
cost tracking, retries, approvals, routing, checkpoints, tracing, and
evaluation.

Use it when your application already owns the surrounding service and needs a
few well-defined LLM execution functions. Do not use it as a retrieval system,
long-running scheduler, provider gateway, or multi-agent runtime. See
[Scope](#scope) for the boundary.

The base install supports Python 3.11 through 3.13 and has no required
third-party runtime dependencies.

## Install

```bash
python -m pip install executionkit
```

Optional extras add only the feature you request:

```bash
python -m pip install "executionkit[httpx]"       # pooled HTTP connections
python -m pip install "executionkit[jsonschema]"  # full tool-argument validation
python -m pip install "executionkit[otel]"        # OpenTelemetry API integration
```

## First call

```python
import asyncio
import os

from executionkit import Provider, consensus


async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ["OPENAI_MODEL"],
    ) as provider:
        result = await consensus(
            provider,
            "Return only the ISO country code for France.",
            num_samples=3,
        )
        print(result.value)
        print(result.metadata["agreement_ratio"])
        print(result.cost)


asyncio.run(main())
```

`result.cost.llm_calls` counts dispatched HTTP attempts, including retries.
For example, three samples cost three calls only when none of the samples is
retried.

See the [quick start](https://tafreeman.github.io/executionkit/getting-started/quickstart/)
for local-provider setup, synchronous wrappers, and the other patterns.

## Patterns

| Function | Use it for |
|---|---|
| [`consensus()`](https://tafreeman.github.io/executionkit/patterns/consensus/) | Run several independent calls and measure exact-answer agreement. |
| [`refine_loop()`](https://tafreeman.github.io/executionkit/patterns/iterative-refinement/) | Generate, score, and revise until a score target or iteration limit is reached. |
| [`react_loop()`](https://tafreeman.github.io/executionkit/patterns/react-loop/) | Let a model request registered async tools inside a bounded loop. |
| [`structured()`](https://tafreeman.github.io/executionkit/patterns/structured/) | Parse a JSON object or array, validate it, and request repairs when needed. |
| [`pipe()`](https://tafreeman.github.io/executionkit/patterns/pipe/) | Pass one pattern result into the next and keep one shared budget. |
| [`map_reduce()`](https://tafreeman.github.io/executionkit/patterns/map-reduce/) | Process independent inputs concurrently, then combine the mapped results. |

Async functions are the primary API. Matching `_sync` wrappers are available
for all six patterns in code that does not already run an event loop.

Every pattern returns `PatternResult`:

```python
result.value       # pattern output
result.score       # optional pattern-specific score
result.cost        # TokenUsage(input_tokens, output_tokens, llm_calls)
result.metadata    # read-only pattern-specific metadata
```

## Execution helpers

| Area | Public API |
|---|---|
| Provider access | `Provider`, `LLMProvider`, `ToolCallingProvider`, `StreamingProvider` |
| Session state | `Kit` |
| Retry and rate control | `RetryConfig`, `TokenBucket` |
| Cost accounting | `TokenUsage`, `CostTracker`, `estimate_cost()` |
| Routing | `Router`, `RouteRule` |
| Dependency-ordered work | `Workflow`, `Step`, `WorkflowCheckpoint` |
| Ordered plans | `Plan`, `PlanStep` |
| Approval | `ApprovalGate`, `ApprovalRequest`, `ApprovalDecision` |
| Tracing | `TraceEvent`, `TraceCallback` |
| Evaluation | `EvalCase`, `EvalReport`, `ConversationScript`, `run_eval_suite()` |

These helpers run inside one process. They do not provide durable scheduling,
distributed coordination, or multi-agent handoff.

## Provider contract

`Provider` sends bearer-authenticated requests to an OpenAI-compatible
`/chat/completions` endpoint. Set `base_url`, `api_key`, and `model` for the
endpoint you use:

```python
provider = Provider(
    base_url="http://localhost:11434/v1",
    model="your-local-model",
)
```

You can also pass any object that implements the `LLMProvider` protocol. A
custom adapter does not need to inherit from an ExecutionKit class.

Provider compatibility varies by endpoint and model. In particular, tool
calling and streaming work only when the endpoint returns the corresponding
OpenAI-format fields. The [provider guide](https://tafreeman.github.io/executionkit/getting-started/providers/)
lists the exact contract and current endpoint examples.

## Tool execution boundary

`react_loop()` executes only the `Tool` objects registered by the caller. The
loop applies these controls before and around each tool call:

- tool names must be unique;
- arguments are checked against a dependency-free JSON Schema subset;
- schemas outside that subset fail closed unless the `jsonschema` extra is
  installed;
- each tool has a timeout;
- calls per round, rounds per run, and observation length are bounded;
- an optional `ApprovalGate` can reject a call before its body runs; and
- tool exceptions become bounded observations containing the exception type,
  not the exception message or traceback.

This protects the model-to-tool boundary. It does not isolate the Python code
inside a tool. Run untrusted tool implementations in a separate process or
container owned by your application.

## MCP and batch integrations

`python -m executionkit.mcp` starts a standard-library-only MCP server over
stdio. It exposes `consensus` and a `react_loop` limited to the package's fixed
demo tools. It does not expose arbitrary caller-defined Python functions.

`AnthropicBatchClient`, `consensus_batch()`, and `map_batch()` use Anthropic's
Message Batches API for offline fan-out jobs. This integration is
Anthropic-specific and separate from the OpenAI-compatible `Provider`.

Read the [MCP guide](https://tafreeman.github.io/executionkit/integrations/mcp/)
and [Message Batches guide](https://tafreeman.github.io/executionkit/integrations/message-batches/)
before using either integration.

## Scope

ExecutionKit intentionally does not provide:

- retrieval, embeddings, or vector storage;
- persistent or distributed workflow scheduling;
- dashboards or spend-management services;
- native adapters for every model provider; or
- multi-agent coordination.

The companion
[agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform)
owns the higher-level runtime concerns. ExecutionKit remains usable on its own.

## Documentation

- [Installation](https://tafreeman.github.io/executionkit/getting-started/installation/)
- [Provider setup](https://tafreeman.github.io/executionkit/getting-started/providers/)
- [Pattern selection](https://tafreeman.github.io/executionkit/patterns/)
- [Execution controls](https://tafreeman.github.io/executionkit/guides/execution-controls/)
- [Evaluation](https://tafreeman.github.io/executionkit/guides/evaluation/)
- [API index](https://tafreeman.github.io/executionkit/api/)
- [Architecture](https://tafreeman.github.io/executionkit/architecture/)
- [Changelog](CHANGELOG.md)

## Development

```bash
python -m pip install -e ".[dev,docs]" pip-audit
python -m ruff check executionkit tests scripts
python -m ruff format --check executionkit tests scripts
python -m mypy --strict executionkit
python scripts/check_doc_facts.py
python scripts/check_lock_parity.py
python -m pytest -q
python -m mkdocs build --strict
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for platform-specific setup and the
optional security checks.

## License

MIT. See [LICENSE](LICENSE).
