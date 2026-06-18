"""Retry configuration and execution with exponential backoff."""

from __future__ import annotations

import asyncio
import inspect
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from executionkit.engine.rate_bucket import TokenBucket

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
        rate_limit_strategy: Optional ``TokenBucket`` strategy used to pace
            requests. When set, :func:`with_retry` acquires a token before each
            attempt and drains the bucket on ``RateLimitError`` so the provider's
            ``retry_after`` cooldown is honoured. ``None`` (default) preserves the
            original behaviour exactly.
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    retryable: tuple[type[Exception], ...] = (RateLimitError, ProviderError)
    rate_limit_strategy: TokenBucket | None = None

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


async def _run_before_attempt(
    callback: Callable[[int], Awaitable[None] | None] | None,
    attempt: int,
) -> None:
    """Invoke an optional per-attempt callback, awaiting async results.

    Any callback return value is ignored; callbacks should return ``None``.
    """
    if callback is None:
        return
    maybe_awaitable = callback(attempt)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


async def with_retry(
    fn: Callable[..., Awaitable[T]],
    config: RetryConfig,
    *args: Any,
    _before_attempt: Callable[[int], Awaitable[None] | None] | None = None,
    **kwargs: Any,
) -> T:
    """Execute an async function with retry logic.

    Args:
        fn: Async callable to execute.
        config: Retry configuration.
        *args: Positional arguments forwarded to *fn*.
        _before_attempt: Optional callback invoked before each attempt
            (1-indexed). Used internally for call accounting and retry budget
            enforcement.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        The return value of *fn*.

    Raises:
        asyncio.CancelledError: Always propagated immediately.
        Exception: Re-raised when retries are exhausted or exception is not retryable.
    """
    if config.max_retries == 0:
        await _run_before_attempt(_before_attempt, 1)
        if config.rate_limit_strategy is not None:
            await config.rate_limit_strategy.acquire()
        return await fn(*args, **kwargs)

    for attempt in range(1, config.max_retries + 1):
        try:
            await _run_before_attempt(_before_attempt, attempt)
            # Pace the request through the bucket (a no-op when full); after a
            # prior drain() this blocks out the provider's retry_after cooldown.
            if config.rate_limit_strategy is not None:
                await config.rate_limit_strategy.acquire()
            return await fn(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not config.should_retry(exc) or attempt == config.max_retries:
                raise
            # Drain immediately on a 429 so the next acquire() honours the
            # cooldown; the jitter/backoff sleep below still runs as before.
            if (
                isinstance(exc, RateLimitError)
                and config.rate_limit_strategy is not None
            ):
                config.rate_limit_strategy.drain(exc.retry_after)
            delay = config.get_delay(attempt)
            if isinstance(exc, RateLimitError):
                delay = max(delay, exc.retry_after or 0.0)
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable")  # pragma: no cover
