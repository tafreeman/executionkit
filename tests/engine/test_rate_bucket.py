"""Tests for the TokenBucket adaptive rate-limit strategy (Item D).

Looping ``acquire()`` paths use a deterministic fake clock (``asyncio.sleep``
advances virtual time) so the Retry-After guarantee is verified for any
rate/capacity rather than relying on coincidental parameter choices.
"""

from __future__ import annotations

import pytest

from executionkit.engine import rate_bucket as rate_bucket_module
from executionkit.engine import retry as retry_module
from executionkit.engine.rate_bucket import TokenBucket
from executionkit.engine.retry import RetryConfig, with_retry
from executionkit.provider import ProviderError, RateLimitError


class _FakeClock:
    """Deterministic monotonic clock; ``sleep`` advances virtual time."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _install_fake_clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    clock = _FakeClock()
    monkeypatch.setattr(rate_bucket_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(rate_bucket_module.asyncio, "sleep", clock.sleep)
    return clock


# ---------------------------------------------------------------------------
# acquire / refill / drain
# ---------------------------------------------------------------------------


async def test_acquire_immediate_when_full(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(rate_bucket_module.asyncio, "sleep", _fake_sleep)
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    await bucket.acquire()
    assert sleeps == []  # a full bucket never blocks


async def test_acquire_waits_when_drained(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _install_fake_clock(monkeypatch)
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    bucket.drain(1.0)  # empties tokens and arms a 1s penalty
    await bucket.acquire()
    assert clock.sleeps  # had to wait at least once


def test_drain_reduces_tokens_by_rate_times_seconds() -> None:
    bucket = TokenBucket(rate=10.0, capacity=100.0)
    before = bucket._tokens
    bucket.drain(2.0)
    assert before - bucket._tokens == pytest.approx(20.0)


def test_drain_floors_at_zero() -> None:
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    bucket.drain(100.0)  # would remove 1000 tokens
    assert bucket._tokens == 0.0


async def test_acquire_after_drain_waits_at_least_retry_after_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _install_fake_clock(monkeypatch)
    bucket = TokenBucket(rate=10.0, capacity=10.0)
    retry_after = 5.0
    bucket.drain(retry_after)
    await bucket.acquire()
    assert sum(clock.sleeps) >= retry_after


# ---------------------------------------------------------------------------
# with_retry integration
# ---------------------------------------------------------------------------


async def test_with_retry_calls_drain_on_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry_module.asyncio, "sleep", _noop_sleep)

    bucket = TokenBucket(rate=100.0, capacity=100.0)
    drain_calls: list[float] = []

    def _spy_drain(seconds: float) -> None:
        drain_calls.append(seconds)

    async def _noop_acquire() -> None:
        return None

    monkeypatch.setattr(bucket, "drain", _spy_drain)
    monkeypatch.setattr(bucket, "acquire", _noop_acquire)

    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RateLimitError("limited", retry_after=2.0)
        return "ok"

    cfg = RetryConfig(max_retries=2, base_delay=0.0, rate_limit_strategy=bucket)
    result = await with_retry(fn, cfg)
    assert result == "ok"
    assert drain_calls == [2.0]


async def test_with_retry_calls_acquire_before_next_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry_module.asyncio, "sleep", _noop_sleep)

    bucket = TokenBucket(rate=100.0, capacity=100.0)
    events: list[str] = []

    async def _spy_acquire() -> None:
        events.append("acquire")

    def _noop_drain(seconds: float) -> None:
        return None

    monkeypatch.setattr(bucket, "acquire", _spy_acquire)
    monkeypatch.setattr(bucket, "drain", _noop_drain)

    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        events.append("attempt")
        if calls == 1:
            raise RateLimitError("limited", retry_after=1.0)
        return "ok"

    cfg = RetryConfig(max_retries=2, base_delay=0.0, rate_limit_strategy=bucket)
    result = await with_retry(fn, cfg)
    assert result == "ok"
    # acquire() runs immediately before every attempt
    assert events == ["acquire", "attempt", "acquire", "attempt"]


async def test_with_retry_unchanged_when_strategy_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry_module.asyncio, "sleep", _noop_sleep)

    calls = 0

    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ProviderError("transient")
        return "ok"

    cfg = RetryConfig(max_retries=3, base_delay=0.0)  # rate_limit_strategy is None
    result = await with_retry(fn, cfg)
    assert result == "ok"
    assert calls == 2
