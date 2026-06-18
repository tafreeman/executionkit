"""Adaptive rate-limit strategy: an asyncio token bucket.

:class:`TokenBucket` is a classic token-bucket rate limiter: tokens refill at a
constant ``rate`` per second up to a maximum ``capacity`` (the burst size).
:meth:`acquire` consumes one token, blocking until one is available.

It additionally honours provider ``Retry-After`` signals.  :meth:`drain` both
removes tokens *and* arms a penalty deadline, so the next :meth:`acquire` blocks
for at least the requested cooldown regardless of ``rate`` or ``capacity`` — the
token reduction alone cannot guarantee a multi-second wait once ``capacity``
exceeds a single token.

This is a deliberately *stateful* primitive: unlike the immutable value types in
:mod:`executionkit.types`, a rate limiter must track elapsed time across calls.
It is **not thread-safe** — it is designed for a single asyncio event loop, where
cooperative scheduling serialises access between ``await`` points.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

_MIN_CAPACITY: float = 1.0
"""Smallest sane capacity: below one token, ``acquire`` could never succeed."""


@dataclass
class TokenBucket:
    """Coroutine-paced token bucket with ``Retry-After`` penalty support.

    Attributes:
        rate: Tokens refilled per second (sustained throughput). Must be > 0.
        capacity: Maximum tokens held — the burst size. Must be >= 1.0 so a
            single-token :meth:`acquire` can always eventually succeed.
    """

    rate: float
    capacity: float
    _tokens: float = field(init=False, repr=False)
    _last_refill: float = field(init=False, repr=False)
    _penalty_until: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.rate <= 0.0:
            raise ValueError(f"rate must be > 0, got {self.rate}")
        if self.capacity < _MIN_CAPACITY:
            raise ValueError(
                f"capacity must be >= {_MIN_CAPACITY}, got {self.capacity}"
            )
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        # No penalty initially: a deadline in the (non-strict) past never blocks.
        self._penalty_until = self._last_refill

    def _refill(self) -> None:
        """Add tokens accrued since the last refill, capped at ``capacity``."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    async def acquire(self) -> None:
        """Block until one token is available, then consume it.

        Honours any active penalty window (see :meth:`drain`) before refilling,
        so a prior ``Retry-After`` cooldown is always respected first.
        """
        while True:
            now = time.monotonic()
            if now < self._penalty_until:
                await asyncio.sleep(self._penalty_until - now)
                continue
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait = (1.0 - self._tokens) / self.rate
            await asyncio.sleep(wait)

    def drain(self, seconds: float) -> None:
        """Force-drain the bucket as if the provider rate-limited us for ``seconds``.

        Called immediately after receiving a
        :class:`~executionkit.errors.RateLimitError` with ``retry_after``.
        Removes ``seconds * rate`` tokens (floored at zero) *and* arms a penalty
        deadline ``seconds`` into the future so the next :meth:`acquire` waits out
        the full cooldown.  ``last_refill`` is advanced so the refill calculation
        on the next :meth:`acquire` does not immediately undo the drain.
        """
        now = time.monotonic()
        self._tokens = max(0.0, self._tokens - seconds * self.rate)
        self._last_refill = now
        # Extend (never shorten) the penalty so repeated 429s accumulate cooldown.
        self._penalty_until = max(self._penalty_until, now + seconds)
