"""ExecutionKit — Composable LLM reasoning patterns."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from executionkit._mock import MockProvider
from executionkit.compose import PatternStep, pipe
from executionkit.cost import CostTracker
from executionkit.engine.convergence import ConvergenceDetector
from executionkit.engine.json_extraction import extract_json
from executionkit.engine.retry import DEFAULT_RETRY, RetryConfig
from executionkit.kit import Kit
from executionkit.patterns.base import checked_complete, validate_score
from executionkit.patterns.consensus import consensus
from executionkit.patterns.react_loop import react_loop
from executionkit.patterns.refine_loop import refine_loop
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
    ToolCall,
    ToolCallingProvider,
)
from executionkit.types import (
    Evaluator,
    PatternResult,
    TokenUsage,
    Tool,
    VotingStrategy,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_RETRY",
    "BudgetExhaustedError",
    "ConsensusFailedError",
    "ConvergenceDetector",
    "CostTracker",
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
    "Provider",
    "ProviderError",
    "RateLimitError",
    "RetryConfig",
    "TokenUsage",
    "Tool",
    "ToolCall",
    "ToolCallingProvider",
    "VotingStrategy",
    "__version__",
    "checked_complete",
    "consensus",
    "consensus_sync",
    "extract_json",
    "pipe",
    "pipe_sync",
    "react_loop",
    "react_loop_sync",
    "refine_loop",
    "refine_loop_sync",
    "validate_score",
]


# ---------------------------------------------------------------------------
# Sync wrapper helper
# ---------------------------------------------------------------------------


def _run_sync(coro: Any) -> Any:
    """Run a coroutine synchronously, raising a helpful error in async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
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
    return cast("PatternResult[str]", _run_sync(consensus(provider, prompt, **kwargs)))


def refine_loop_sync(
    provider: LLMProvider, prompt: str, **kwargs: Any
) -> PatternResult[str]:
    """Synchronous wrapper for :func:`refine_loop`."""
    return cast(
        "PatternResult[str]", _run_sync(refine_loop(provider, prompt, **kwargs))
    )


def react_loop_sync(
    provider: ToolCallingProvider,
    prompt: str,
    tools: Sequence[Tool] = (),
    **kwargs: Any,
) -> PatternResult[str]:
    """Synchronous wrapper for :func:`react_loop`."""
    return cast(
        "PatternResult[str]",
        _run_sync(react_loop(provider, prompt, tools, **kwargs)),
    )


def pipe_sync(
    provider: LLMProvider, prompt: str, *steps: Any, **kwargs: Any
) -> PatternResult[Any]:
    """Synchronous wrapper for :func:`pipe`."""
    return cast(
        "PatternResult[Any]", _run_sync(pipe(provider, prompt, *steps, **kwargs))
    )
