# Execution helper API

## Session

::: executionkit.kit.Kit

`Kit` tracks cumulative usage for calls made through its methods. Direct calls
through `kit.provider` are not included.

## Retry, pacing, and cost

::: executionkit.engine.retry.RetryConfig

`DEFAULT_RETRY` is:

```python
RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
)
```

`max_retries` counts calls after the initial attempt. The default therefore
allows at most four dispatched attempts for a retryable failure.

::: executionkit.engine.rate_bucket.TokenBucket

::: executionkit.cost.CostTracker

::: executionkit.cost.estimate_cost

::: executionkit.engine.convergence.ConvergenceDetector

`CostTracker` is mutable and is safe for the package's asyncio accounting
sequence. It is not thread-safe.

## Routing

::: executionkit.routing.RouteRule

::: executionkit.routing.Router

## Workflow

::: executionkit.workflow.Step

::: executionkit.workflow.Workflow

::: executionkit.workflow.WorkflowCheckpoint

::: executionkit.workflow.WorkflowResult

## Planning

::: executionkit.planning.PlanStep

::: executionkit.planning.Plan

::: executionkit.planning.PlanResult

## Approval

::: executionkit.approval.ApprovalRequest

::: executionkit.approval.ApprovalDecision

::: executionkit.approval.ApprovalGate

::: executionkit.approval.ApprovalDeniedError

::: executionkit.approval.ApprovalTimeoutError

## Tracing

::: executionkit.observability.TraceEvent

`TraceCallback` accepts a `TraceEvent` and may return `None` or an awaitable.

::: executionkit.observability.emit_trace

The lower-level OpenTelemetry helpers live in
`executionkit.observability`. They are not package-root exports:

::: executionkit.observability.llm_span

::: executionkit.observability.record_llm_span_attributes

## Exceptions

All package exceptions derive from `ExecutionKitError`. Each instance carries
`cost` and `metadata`.

```text
ExecutionKitError
├── LLMError
│   ├── RateLimitError
│   ├── PermanentError
│   └── ProviderError
└── PatternError
    ├── BudgetExhaustedError
    ├── ConsensusFailedError
    └── MaxIterationsError
```

`ApprovalDeniedError` and `ApprovalTimeoutError` also derive from
`ExecutionKitError`.

::: executionkit.errors.ExecutionKitError

::: executionkit.errors.LLMError

::: executionkit.errors.RateLimitError

::: executionkit.errors.PermanentError

::: executionkit.errors.ProviderError

::: executionkit.errors.PatternError

::: executionkit.errors.BudgetExhaustedError

::: executionkit.errors.ConsensusFailedError

::: executionkit.errors.MaxIterationsError
