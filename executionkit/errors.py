"""ExecutionKit exception hierarchy.

The error classes live in this module so callers can import them without
loading the HTTP client. ``executionkit.provider`` re-exports them for
backward compatibility.
"""

from __future__ import annotations

from typing import Any

from executionkit.types import TokenUsage


class ExecutionKitError(Exception):
    """Base exception for all ExecutionKit errors."""

    def __init__(
        self,
        message: str,
        *,
        cost: TokenUsage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.cost: TokenUsage = cost if cost is not None else TokenUsage()
        self.metadata: dict[str, Any] = metadata if metadata is not None else {}


class LLMError(ExecutionKitError):
    """Errors originating from LLM provider communication."""


class RateLimitError(LLMError):
    """Provider returned HTTP 429 — retryable after ``retry_after`` seconds."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float = 1.0,
        cost: TokenUsage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, cost=cost, metadata=metadata)
        self.retry_after: float = retry_after


class PermanentError(LLMError):
    """Non-retryable provider error (e.g. 401 authentication failure)."""


class ProviderError(LLMError):
    """Catch-all retryable provider error for unexpected HTTP failures."""


class PatternError(ExecutionKitError):
    """Errors raised by reasoning pattern logic."""


class BudgetExhaustedError(PatternError):
    """Token or call budget exceeded."""


class ConsensusFailedError(PatternError):
    """Consensus pattern could not reach agreement."""


class MaxIterationsError(PatternError):
    """Loop pattern exceeded its iteration limit."""
