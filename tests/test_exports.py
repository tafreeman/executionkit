from __future__ import annotations

import executionkit


def test_public_api_surface() -> None:
    """Smoke-test that all documented public names are importable."""
    expected = [
        "BudgetExhaustedError",
        "ConsensusFailedError",
        "ConvergenceDetector",
        "CostTracker",
        "DEFAULT_RETRY",
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
    missing = [name for name in expected if not hasattr(executionkit, name)]
    assert missing == [], f"Missing from public API: {missing}"


def test_all_entries_are_importable() -> None:
    """Every name in __all__ must actually be importable from the package."""
    import importlib

    mod = importlib.import_module("executionkit")
    missing = [name for name in mod.__all__ if not hasattr(mod, name)]
    assert missing == [], f"Names in __all__ but not importable: {missing}"
