"""Tests for async concurrency behaviour in gather_resilient and gather_strict."""

from __future__ import annotations

import asyncio

import pytest

from executionkit.engine.parallel import gather_resilient, gather_strict

# ---------------------------------------------------------------------------
# Semaphore limit verification
# ---------------------------------------------------------------------------


class TestGatherResilientConcurrencyLimit:
    async def test_semaphore_limits_to_1(self) -> None:
        concurrent = 0
        max_seen = 0

        async def task() -> str:
            nonlocal concurrent, max_seen
            concurrent += 1
            max_seen = max(max_seen, concurrent)
            await asyncio.sleep(0.02)
            concurrent -= 1
            return "ok"

        await gather_resilient([task() for _ in range(5)], max_concurrency=1)
        assert max_seen == 1

    async def test_semaphore_limits_to_2(self) -> None:
        concurrent = 0
        max_seen = 0

        async def task() -> str:
            nonlocal concurrent, max_seen
            concurrent += 1
            max_seen = max(max_seen, concurrent)
            await asyncio.sleep(0.02)
            concurrent -= 1
            return "ok"

        await gather_resilient([task() for _ in range(8)], max_concurrency=2)
        assert max_seen <= 2

    async def test_semaphore_limits_to_n(self) -> None:
        """Max concurrency of N should never exceed N active tasks."""
        concurrent = 0
        max_seen = 0
        n = 4

        async def task() -> str:
            nonlocal concurrent, max_seen
            concurrent += 1
            max_seen = max(max_seen, concurrent)
            await asyncio.sleep(0.01)
            concurrent -= 1
            return "done"

        await gather_resilient([task() for _ in range(12)], max_concurrency=n)
        assert max_seen <= n

    async def test_default_concurrency_allows_many(self) -> None:
        """Default max_concurrency=10 allows up to 10 concurrent tasks."""
        concurrent = 0
        max_seen = 0

        async def task() -> str:
            nonlocal concurrent, max_seen
            concurrent += 1
            max_seen = max(max_seen, concurrent)
            await asyncio.sleep(0.01)
            concurrent -= 1
            return "ok"

        # 10 tasks with default concurrency=10 — all can run in parallel
        await gather_resilient([task() for _ in range(10)])
        assert max_seen <= 10


class TestGatherStrictConcurrencyLimit:
    async def test_semaphore_limits_to_1(self) -> None:
        concurrent = 0
        max_seen = 0

        async def task() -> str:
            nonlocal concurrent, max_seen
            concurrent += 1
            max_seen = max(max_seen, concurrent)
            await asyncio.sleep(0.02)
            concurrent -= 1
            return "ok"

        await gather_strict([task() for _ in range(5)], max_concurrency=1)
        assert max_seen == 1

    async def test_semaphore_limits_to_3(self) -> None:
        concurrent = 0
        max_seen = 0

        async def task() -> str:
            nonlocal concurrent, max_seen
            concurrent += 1
            max_seen = max(max_seen, concurrent)
            await asyncio.sleep(0.01)
            concurrent -= 1
            return "ok"

        await gather_strict([task() for _ in range(9)], max_concurrency=3)
        assert max_seen <= 3


# ---------------------------------------------------------------------------
# CancelledError propagation in gather_resilient
# ---------------------------------------------------------------------------


class TestGatherResilientCancellation:
    async def test_cancelled_error_propagates(self) -> None:
        """CancelledError on the outer task propagates through gather_resilient."""

        async def long_task() -> str:
            await asyncio.sleep(10)
            return "never"

        async def run_and_cancel() -> None:
            task = asyncio.create_task(
                gather_resilient([long_task(), long_task()], max_concurrency=2)
            )
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        await run_and_cancel()

    async def test_individual_task_exception_not_cancelled_error(self) -> None:
        """A ValueError inside a task is returned as a value, not raised."""

        async def fail() -> str:
            raise ValueError("inner error")

        async def ok() -> str:
            return "fine"

        results = await gather_resilient([fail(), ok()])
        assert isinstance(results[0], ValueError)
        assert results[1] == "fine"


# ---------------------------------------------------------------------------
# ExceptionGroup unwrapping in gather_strict
# ---------------------------------------------------------------------------


class TestGatherStrictExceptionUnwrapping:
    async def test_single_exception_unwrapped_from_exception_group(self) -> None:
        """When exactly one task fails, its exception is raised directly."""

        async def ok() -> str:
            return "fine"

        async def fail() -> str:
            raise ValueError("only one failure")

        with pytest.raises(ValueError, match="only one failure"):
            await gather_strict([ok(), fail(), ok()])

    async def test_two_exceptions_raises_exception_group(self) -> None:
        """When two tasks fail, ExceptionGroup is raised (not unwrapped)."""

        async def fail(msg: str) -> str:
            raise RuntimeError(msg)

        async def ok() -> str:
            return "ok"

        with pytest.raises(ExceptionGroup) as exc_info:
            await gather_strict([fail("first"), fail("second"), ok()])

        eg = exc_info.value
        assert len(eg.exceptions) == 2

    async def test_three_exceptions_raises_exception_group(self) -> None:
        """ExceptionGroup with 3 failures is raised as-is."""

        async def fail() -> str:
            raise ValueError("fail")

        with pytest.raises(ExceptionGroup) as exc_info:
            await gather_strict([fail(), fail(), fail()])

        assert len(exc_info.value.exceptions) == 3

    async def test_unwrapped_exception_is_not_exception_group(self) -> None:
        """Verify single-exception case is a plain exception, not ExceptionGroup."""

        async def fail() -> str:
            raise TypeError("type error")

        async def ok() -> str:
            return "ok"

        exc_caught = None
        try:
            await gather_strict([ok(), fail()])
        except ExceptionGroup:
            pytest.fail("Should not have raised ExceptionGroup for single failure")
        except TypeError as e:
            exc_caught = e

        assert exc_caught is not None
        assert str(exc_caught) == "type error"

    async def test_exception_type_preserved_after_unwrap(self) -> None:
        """The unwrapped exception retains its original type."""

        async def fail() -> str:
            raise KeyError("missing_key")

        with pytest.raises(KeyError):
            await gather_strict([fail()])

    async def test_no_failures_returns_all_results(self) -> None:
        async def task(n: int) -> int:
            return n

        results = await gather_strict([task(i) for i in range(5)])
        assert results == [0, 1, 2, 3, 4]
