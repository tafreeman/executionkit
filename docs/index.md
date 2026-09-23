# ExecutionKit

ExecutionKit is an async Python library for common LLM call patterns and small
in-process workflows. It provides:

- six bounded call patterns;
- an HTTP client for OpenAI-compatible chat-completions endpoints;
- cost, retry, rate-limit, trace, approval, and checkpoint helpers;
- repeatable evaluation helpers; and
- optional MCP, Anthropic Message Batches, JSON Schema, HTTPX, and
  OpenTelemetry integrations.

The base package supports Python 3.11 through 3.13 and has no required
third-party runtime dependencies.

!!! note "Release status"
    `pip install executionkit` currently installs **0.4.0** (2026-09-23). See
    the `[0.4.0]` section of
    [CHANGELOG.md](https://github.com/tafreeman/executionkit/blob/main/CHANGELOG.md#040---2026-09-23)
    for the full list of what changed since 0.3.0 and how to migrate. The
    [configuration reference](api/configuration.md#retryconfig) and
    [Claude Agent SDK integration](integrations/claude-agent-sdk.md) call out
    the specific behavior changes.

## Install and run

```bash
python -m pip install executionkit
```

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

Expected output (token counts depend on the endpoint; the shape does not):

```text
FR
1.0
TokenUsage(input_tokens=..., output_tokens=..., llm_calls=3)
```

Read [Installation](getting-started/installation.md) for optional extras and
[Provider setup](getting-started/providers.md) for other endpoints.

## Choose a pattern

| Need | Function | Guide |
|---|---|---|
| Compare exact answers from independent calls | `consensus()` | [Consensus](patterns/consensus.md) |
| Revise an answer until a score target or limit | `refine_loop()` | [Iterative refinement](patterns/iterative-refinement.md) |
| Let a model request registered tools | `react_loop()` | [ReAct tool loop](patterns/react-loop.md) |
| Parse, validate, and repair JSON | `structured()` | [Structured output](patterns/structured.md) |
| Pass one result into the next pattern | `pipe()` | [Pipe](patterns/pipe.md) |
| Process independent inputs, then combine them | `map_reduce()` | [Map-reduce](patterns/map-reduce.md) |

All six functions are async. Each returns a `PatternResult` with:

- `value`: the output;
- `score`: an optional pattern-specific score;
- `cost`: input tokens, output tokens, and dispatched model-call attempts; and
- `metadata`: a read-only mapping documented by the pattern.

Matching `_sync` wrappers are available for code that does not already run an
event loop.

## Understand the limits

ExecutionKit makes specific guarantees, not general claims about model quality.

- `consensus()` compares normalized response text. It does not judge semantic
  equivalence.
- `refine_loop()` is only as useful as its evaluator. The built-in evaluator
  is model-based and should not authorize high-impact decisions.
- `react_loop()` bounds and validates the model-to-tool boundary. It does not
  isolate caller-written Python tools.
- `structured()` guarantees that returned data parsed and passed the supplied
  validator. It does not make the data factually correct.
- token budgets use provider-reported counts; call budgets count dispatched
  attempts, including retries.
- streaming helpers emit one model generation. They do not run the complete
  consensus, map-reduce, structured-output, or tool-execution algorithms.

Read the individual pattern page before choosing defaults for production code.

## Add execution controls

The package also provides small helpers around pattern calls:

| Task | API |
|---|---|
| Keep cumulative conversation and usage state | `Kit` |
| Retry selected errors | `RetryConfig` |
| Pace calls | `TokenBucket` |
| Select a provider | `Router`, `RouteRule` |
| Run dependency-ordered steps | `Workflow`, `Step` |
| Save and resume workflow progress | `WorkflowCheckpoint` |
| Run ordered steps | `Plan`, `PlanStep` |
| Approve work before it runs | `ApprovalGate` |
| Observe calls and steps | `TraceEvent`, `TraceCallback` |
| Run repeatable checks | `EvalCase`, `EvalReport` |

Start with:

- [Execution controls](guides/execution-controls.md)
- [Workflows and approvals](guides/workflows.md)
- [Evaluation](guides/evaluation.md)
- [Streaming](guides/streaming.md)

## Use an integration

The [MCP server](integrations/mcp.md) exposes two package operations over
stdio without adding the MCP SDK as a dependency.

The [Anthropic Message Batches](integrations/message-batches.md) integration
submits offline fan-out work through Anthropic's native batch API. It is
separate from the OpenAI-compatible `Provider`.

Optional extras enable connection pooling, full JSON Schema validation, or
OpenTelemetry API spans. The package keeps a working standard-library path
when those extras are absent.

## Package boundary

ExecutionKit runs inside one Python process. It does not include:

- retrieval, embeddings, or vector storage;
- persistent or distributed scheduling;
- dashboards or spend-management services;
- native adapters for every model provider; or
- multi-agent coordination.

Use the package inside a larger application when you need those capabilities.
The [Architecture](architecture.md) page explains the boundary between modules
and the extension points intended for callers.

## Reference

- [API index](api/index.md)
- [Configuration defaults](api/configuration.md)
- [Architecture decisions](adr/README.md)
- [Security policy](security.md)
- [Changelog](changelog.md)
- [Contributing](contributing.md)
