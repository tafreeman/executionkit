"""ExecutionKit — Composable LLM reasoning patterns."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, TypeVar

from executionkit._mock import MockProvider
from executionkit.approval import (
    ApprovalDecision,
    ApprovalDeniedError,
    ApprovalGate,
    ApprovalRequest,
    ApprovalTimeoutError,
)
from executionkit.batches import AnthropicBatchClient, consensus_batch, map_batch
from executionkit.compose import PatternStep, pipe
from executionkit.cost import CostTracker, estimate_cost
from executionkit.engine.convergence import ConvergenceDetector
from executionkit.engine.json_extraction import extract_json
from executionkit.engine.rate_bucket import TokenBucket
from executionkit.engine.retry import DEFAULT_RETRY, RetryConfig
from executionkit.evals import (
    ConversationScript,
    EvalCase,
    EvalReport,
    EvalResult,
    Turn,
    live_provider_from_env,
    run_conversation_script,
    run_eval_suite,
)
from executionkit.kit import Kit
from executionkit.observability import TraceCallback, TraceEvent, emit_trace
from executionkit.patterns.base import (
    checked_complete,
    checked_stream,
    validate_score,
)
from executionkit.patterns.consensus import consensus
from executionkit.patterns.map_reduce import map_reduce
from executionkit.patterns.react_loop import react_loop
from executionkit.patterns.refine_loop import refine_loop
from executionkit.patterns.structured import structured
from executionkit.planning import Plan, PlanResult, PlanStep
from executionkit.provider import (
    BudgetExhaustedError,
    ConsensusFailedError,
    ExecutionKitError,
    LLMError,
    LLMProvider,
    LLMResponse,
    MaxIterationsError,
    PatternError,
    PermanentError,
    Provider,
    ProviderError,
    RateLimitError,
    StreamingProvider,
    ToolCall,
    ToolCallingProvider,
)
from executionkit.routing import Router, RouteRule
from executionkit.types import (
    CheckpointCallback,
    Evaluator,
    PatternResult,
    StreamingPatternResult,
    TerminationReason,
    TokenUsage,
    Tool,
    VotingStrategy,
)
from executionkit.workflow import Step, Workflow, WorkflowCheckpoint, WorkflowResult

if TYPE_CHECKING:
    from collections.abc import Coroutine, Sequence

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_RETRY",
    "AnthropicBatchClient",
    "ApprovalDecision",
    "ApprovalDeniedError",
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalTimeoutError",
    "BudgetExhaustedError",
    "CheckpointCallback",
    "ConsensusFailedError",
    "ConvergenceDetector",
    "ConversationScript",
    "CostTracker",
    "EvalCase",
    "EvalReport",
    "EvalResult",
    "Evaluator",
    "ExecutionKitError",
    "Kit",
    "LLMError",
    "LLMProvider",
    "LLMResponse",
    "MaxIterationsError",
    "MockProvider",
    "PatternError",
    "PatternResult",
    "PatternStep",
    "PermanentError",
    "Plan",
    "PlanResult",
    "PlanStep",
    "Provider",
    "ProviderError",
    "RateLimitError",
    "RetryConfig",
    "RouteRule",
    "Router",
    "Step",
    "StreamingPatternResult",
    "StreamingProvider",
    "TerminationReason",
    "TokenBucket",
    "TokenUsage",
    "Tool",
    "ToolCall",
    "ToolCallingProvider",
    "TraceCallback",
    "TraceEvent",
    "Turn",
    "VotingStrategy",
    "Workflow",
    "WorkflowCheckpoint",
    "WorkflowResult",
    "__version__",
    "checked_complete",
    "checked_stream",
    "consensus",
    "consensus_batch",
    "consensus_sync",
    "emit_trace",
    "estimate_cost",
    "extract_json",
    "live_provider_from_env",
    "map_batch",
    "map_reduce",
    "map_reduce_sync",
    "pipe",
    "pipe_sync",
    "react_loop",
    "react_loop_sync",
    "refine_loop",
    "refine_loop_sync",
    "run_conversation_script",
    "run_eval_suite",
    "structured",
    "structured_sync",
    "validate_score",
]


# ---------------------------------------------------------------------------
# Sync wrapper helper
# ---------------------------------------------------------------------------


_T = TypeVar("_T")


def _run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine synchronously, raising a helpful error in async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        # The caller built *coro* eagerly (it is an argument), so close it
        # before raising — otherwise it is garbage-collected un-awaited and
        # emits a spurious "coroutine was never awaited" RuntimeWarning.
        coro.close()
        raise RuntimeError(
            "Cannot use sync wrappers inside an async context (e.g., Jupyter). "
            "Use 'await' instead, or install nest_asyncio and call "
            "nest_asyncio.apply()."
        )
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Sync wrappers
# ---------------------------------------------------------------------------


def consensus_sync(
    provider: LLMProvider, prompt: str, **kwargs: Any
) -> PatternResult[str]:
    """Synchronous wrapper for :func:`consensus`."""
    return _run_sync(consensus(provider, prompt, **kwargs))


def refine_loop_sync(
    provider: LLMProvider, prompt: str, **kwargs: Any
) -> PatternResult[str]:
    """Synchronous wrapper for :func:`refine_loop`."""
    return _run_sync(refine_loop(provider, prompt, **kwargs))


def react_loop_sync(
    provider: ToolCallingProvider,
    prompt: str,
    tools: Sequence[Tool] = (),
    **kwargs: Any,
) -> PatternResult[str]:
    """Synchronous wrapper for :func:`react_loop`."""
    return _run_sync(react_loop(provider, prompt, tools, **kwargs))


def pipe_sync(
    provider: LLMProvider, prompt: str, *steps: Any, **kwargs: Any
) -> PatternResult[Any]:
    """Synchronous wrapper for :func:`pipe`."""
    return _run_sync(pipe(provider, prompt, *steps, **kwargs))


def structured_sync(
    provider: LLMProvider, prompt: str, **kwargs: Any
) -> PatternResult[Any]:
    """Synchronous wrapper for :func:`structured`."""
    return _run_sync(structured(provider, prompt, **kwargs))


def map_reduce_sync(
    provider: LLMProvider,
    inputs: Sequence[str],
    **kwargs: Any,
) -> PatternResult[str]:
    """Synchronous wrapper for :func:`map_reduce`."""
    return _run_sync(map_reduce(provider, inputs, **kwargs))
