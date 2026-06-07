# Core API

This page is auto-generated from docstrings via [mkdocstrings](https://mkdocstrings.github.io). Source-of-truth lives in the Python files.

## Patterns

### `consensus`

::: executionkit.patterns.consensus.consensus

### `refine_loop`

::: executionkit.patterns.refine_loop.refine_loop

### `react_loop`

::: executionkit.patterns.react_loop.react_loop

### `structured`

::: executionkit.patterns.structured.structured

### `pipe`

::: executionkit.compose.pipe

::: executionkit.compose.PatternStep

## Sync wrappers

```python
from executionkit import (
    consensus_sync,
    refine_loop_sync,
    react_loop_sync,
    structured_sync,
    pipe_sync,
)
```

Each sync wrapper takes the same arguments as its async counterpart and runs it via `asyncio.run`. They raise `RuntimeError` when called inside a running event loop — use `await` directly there.

## Value types

::: executionkit.types.PatternResult

::: executionkit.types.TokenUsage

::: executionkit.types.Tool

::: executionkit.types.VotingStrategy

::: executionkit.types.Evaluator

## Evals

::: executionkit.evals.EvalCase

::: executionkit.evals.EvalResult

::: executionkit.evals.EvalReport

::: executionkit.evals.run_eval_suite

::: executionkit.evals.live_provider_from_env

## Observability

::: executionkit.observability.TraceEvent

::: executionkit.observability.TraceCallback

::: executionkit.observability.emit_trace

## Routing

::: executionkit.routing.RouteRule

::: executionkit.routing.Router

## Workflow and planning

::: executionkit.workflow.Step

::: executionkit.workflow.Workflow

::: executionkit.workflow.WorkflowResult

::: executionkit.planning.PlanStep

::: executionkit.planning.Plan

::: executionkit.planning.PlanResult

## Approval

::: executionkit.approval.ApprovalRequest

::: executionkit.approval.ApprovalDecision

::: executionkit.approval.ApprovalGate

::: executionkit.approval.ApprovalDeniedError

## Session

::: executionkit.kit.Kit

## Cost tracking

::: executionkit.cost.CostTracker

## Engine helpers

::: executionkit.engine.convergence.ConvergenceDetector

::: executionkit.engine.retry.RetryConfig

::: executionkit.engine.json_extraction.extract_json

## Errors

All exceptions inherit from `ExecutionKitError` and carry `.cost` (`TokenUsage` accumulated up to the failure) and `.metadata` (dict).

| Exception | Cause |
|-----------|-------|
| `ExecutionKitError` | Base for all errors. |
| `LLMError` | Base for provider communication errors. |
| `RateLimitError` | HTTP 429 — retryable. Carries `retry_after`. |
| `PermanentError` | HTTP 401/403/404 — not retryable. |
| `ProviderError` | Unexpected HTTP failure — retryable. |
| `PatternError` | Base for pattern logic errors. |
| `BudgetExhaustedError` | Token or call budget exceeded. |
| `ConsensusFailedError` | Unanimous strategy could not agree. |
| `MaxIterationsError` | `react_loop` exhausted `max_rounds` without a final answer. |

::: executionkit.provider.ExecutionKitError

::: executionkit.provider.RateLimitError

::: executionkit.provider.BudgetExhaustedError

::: executionkit.provider.ConsensusFailedError

::: executionkit.provider.MaxIterationsError
