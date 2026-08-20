# Public API index

The package root is the stable import surface:

```python
from executionkit import Provider, TokenUsage, consensus
```

Names listed here come from `executionkit.__all__`. Import internal modules
only when a guide explicitly identifies an advanced extension point.

## Patterns

| Name | Purpose | Reference |
|---|---|---|
| `consensus` | Vote across independent completions. | [Patterns](core.md) |
| `refine_loop` | Generate, score, and revise. | [Patterns](core.md) |
| `react_loop` | Run a bounded model/tool loop. | [Patterns](core.md) |
| `structured` | Parse, validate, and repair JSON. | [Patterns](core.md) |
| `pipe` | Pass one pattern result to the next. | [Patterns](core.md) |
| `map_reduce` | Map across inputs and reduce the results. | [Patterns](core.md) |
| `consensus_sync` | Synchronous wrapper for `consensus`. | [Patterns](core.md) |
| `refine_loop_sync` | Synchronous wrapper for `refine_loop`. | [Patterns](core.md) |
| `react_loop_sync` | Synchronous wrapper for `react_loop`. | [Patterns](core.md) |
| `structured_sync` | Synchronous wrapper for `structured`. | [Patterns](core.md) |
| `pipe_sync` | Synchronous wrapper for `pipe`. | [Patterns](core.md) |
| `map_reduce_sync` | Synchronous wrapper for `map_reduce`. | [Patterns](core.md) |

## Pattern values and protocols

| Name | Purpose | Reference |
|---|---|---|
| `PatternResult` | Completed pattern value, score, cost, and metadata. | [Patterns](core.md) |
| `StreamingPatternResult` | Async text stream with a live cost view. | [Patterns](core.md) |
| `TokenUsage` | Input-token, output-token, and call counts. | [Patterns](core.md) |
| `Tool` | Registered async tool definition. | [Patterns](core.md) |
| `VotingStrategy` | `majority` or `unanimous`. | [Patterns](core.md) |
| `TerminationReason` | Reason a loop stopped. | [Patterns](core.md) |
| `Evaluator` | Async response-score callback type. | [Patterns](core.md) |
| `CheckpointCallback` | Loop checkpoint callback type. | [Patterns](core.md) |
| `PatternStep` | Callable protocol accepted by `pipe`. | [Patterns](core.md) |

## Providers and responses

| Name | Purpose | Reference |
|---|---|---|
| `Provider` | OpenAI-compatible chat-completions HTTP client. | [Providers](adapters.md) |
| `LLMProvider` | Structural protocol for non-streaming providers. | [Providers](adapters.md) |
| `ToolCallingProvider` | Provider protocol with tool-call support. | [Providers](adapters.md) |
| `StreamingProvider` | Provider protocol with an async text stream. | [Providers](adapters.md) |
| `LLMResponse` | Parsed provider response. | [Providers](adapters.md) |
| `ToolCall` | Parsed model-requested tool call. | [Providers](adapters.md) |
| `MockProvider` | Scripted provider for tests. | [Providers](adapters.md) |
| `ClaudeAgentProvider` | Claude Agent SDK transport authenticated by a Claude subscription sign-in. | [Providers](adapters.md) |

## Session and execution controls

| Name | Purpose | Reference |
|---|---|---|
| `Kit` | Provider session with cumulative usage and optional conversation state. | [Execution helpers](execution.md) |
| `RetryConfig` | Retry count, delay, exception, and rate-limit policy. | [Execution helpers](execution.md) |
| `DEFAULT_RETRY` | Default retry configuration. | [Execution helpers](execution.md) |
| `TokenBucket` | Async call pacing and cooldown. | [Execution helpers](execution.md) |
| `CostTracker` | Mutable token and call accumulator. | [Execution helpers](execution.md) |
| `estimate_cost` | Apply caller-supplied token rates. | [Execution helpers](execution.md) |
| `ConvergenceDetector` | Score-threshold and stalled-progress detector. | [Execution helpers](execution.md) |
| `extract_json` | Extract a JSON object or array from model text. | [Patterns](core.md) |
| `validate_score` | Require a finite score in `[0.0, 1.0]`. | [Patterns](core.md) |
| `checked_complete` | Advanced budgeted/retried completion helper. | [Patterns](core.md) |
| `checked_stream` | Advanced budgeted/retried streaming helper. | [Patterns](core.md) |

## Routing, workflows, plans, and approval

| Name | Purpose | Reference |
|---|---|---|
| `RouteRule` | Named provider-selection predicate. | [Execution helpers](execution.md) |
| `Router` | Select a provider and optionally run a pattern. | [Execution helpers](execution.md) |
| `Step` | Named workflow step with dependencies. | [Execution helpers](execution.md) |
| `Workflow` | Run steps after their dependencies complete. | [Execution helpers](execution.md) |
| `WorkflowCheckpoint` | Workflow progress snapshot with `to_dict()` and `from_dict()`. | [Execution helpers](execution.md) |
| `WorkflowResult` | Workflow outputs and total usage. | [Execution helpers](execution.md) |
| `PlanStep` | Named ordered plan step. | [Execution helpers](execution.md) |
| `Plan` | Run plan steps in order. | [Execution helpers](execution.md) |
| `PlanResult` | Plan outputs and total usage. | [Execution helpers](execution.md) |
| `ApprovalRequest` | Proposed action sent to an approval callback. | [Execution helpers](execution.md) |
| `ApprovalDecision` | Approval result and reason. | [Execution helpers](execution.md) |
| `ApprovalGate` | Sync-or-async approval callback with timeout policy. | [Execution helpers](execution.md) |

## Tracing

| Name | Purpose | Reference |
|---|---|---|
| `TraceEvent` | Event kind and read-only payload. | [Execution helpers](execution.md) |
| `TraceCallback` | Sync-or-async event callback type. | [Execution helpers](execution.md) |
| `emit_trace` | Invoke a trace callback when present. | [Execution helpers](execution.md) |

## Evaluation

| Name | Purpose | Reference |
|---|---|---|
| `EvalCase` | One run/check pair. | [Evaluation](evaluation.md) |
| `EvalResult` | One case result. | [Evaluation](evaluation.md) |
| `EvalReport` | Aggregate results and accuracy. | [Evaluation](evaluation.md) |
| `run_eval_suite` | Run cases in order. | [Evaluation](evaluation.md) |
| `Turn` | One checked conversation turn. | [Evaluation](evaluation.md) |
| `ConversationScript` | Ordered conversation turns. | [Evaluation](evaluation.md) |
| `run_conversation_script` | Evaluate a script with one `Kit`. | [Evaluation](evaluation.md) |
| `live_provider_from_env` | Build an opt-in live provider from environment variables. | [Evaluation](evaluation.md) |

## Anthropic Message Batches

| Name | Purpose | Reference |
|---|---|---|
| `AnthropicBatchClient` | Minimal native Message Batches HTTP client. | [Batch API](batches.md) |
| `consensus_batch` | Run consensus samples as one batch job. | [Batch API](batches.md) |
| `map_batch` | Submit several prompts and return ordered responses. | [Batch API](batches.md) |

## Exceptions

| Name | Meaning | Reference |
|---|---|---|
| `ExecutionKitError` | Base package exception. | [Execution helpers](execution.md) |
| `LLMError` | Base provider-call exception. | [Execution helpers](execution.md) |
| `RateLimitError` | HTTP 429 with `retry_after`. | [Execution helpers](execution.md) |
| `PermanentError` | Non-retryable provider error. | [Execution helpers](execution.md) |
| `ProviderError` | Retryable transport or provider error. | [Execution helpers](execution.md) |
| `PatternError` | Base pattern exception. | [Execution helpers](execution.md) |
| `BudgetExhaustedError` | A token or call budget blocked another attempt. | [Execution helpers](execution.md) |
| `ConsensusFailedError` | Unanimous consensus was not reached. | [Execution helpers](execution.md) |
| `MaxIterationsError` | A bounded loop ended without a final answer. | [Execution helpers](execution.md) |
| `ApprovalDeniedError` | A required approval was denied. | [Execution helpers](execution.md) |
| `ApprovalTimeoutError` | An approval timed out under the `raise` policy. | [Execution helpers](execution.md) |

## Package information

`__version__` is the installed package version.
