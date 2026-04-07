"""Retry configuration and execution with exponential backoff."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from executionkit.provider import ProviderError, RateLimitError

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    """Immutable retry configuration with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts. 0 means no retries.
        base_delay: Base delay in seconds before first retry.
        max_delay: Maximum delay cap in seconds.
        exponential_base: Multiplier for exponential backoff.
        retryable: Tuple of exception types that trigger retries.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable: tuple[type[Exception], ...] = (RateLimitError, ProviderError)

    def should_retry(self, exc: Exception) -> bool:
        """Check whether the given exception is retryable."""
        return isinstance(exc, self.retryable)

    def get_delay(self, attempt: int) -> float:
        """Calculate jittered backoff delay for the given attempt (1-indexed).

        Uses full jitter (random value in [0, capped_exponential]) to prevent
        thundering-herd effects when multiple coroutines retry simultaneously.
        """
        cap = min(
            self.base_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay,
        )
        return random.uniform(0.0, cap)  # noqa: S311


DEFAULT_RETRY: RetryConfig = RetryConfig()


async def with_retry(
    fn: Callable[..., Awaitable[T]],
    config: RetryConfig,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute an async function with retry logic.

    Args:
        fn: Async callable to execute.
        config: Retry configuration.
        *args: Positional arguments forwarded to *fn*.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        The return value of *fn*.

    Raises:
        asyncio.CancelledError: Always propagated immediately.
        Exception: Re-raised when retries are exhausted or exception is not retryable.
    """
    if config.max_retries == 0:
        return await fn(*args, **kwargs)

    for attempt in range(1, config.max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not config.should_retry(exc) or attempt == config.max_retries:
                raise
            await asyncio.sleep(config.get_delay(attempt))

    raise RuntimeError("unreachable")  # pragma: no cover
