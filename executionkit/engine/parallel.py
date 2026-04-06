"""Parallel execution utilities with concurrency limiting."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine


async def gather_resilient(
    coros: list[Coroutine[Any, Any, Any]],
    max_concurrency: int = 10,
) -> list[Any | BaseException]:
    """Run coroutines concurrently, returning exceptions as values.

    Uses ``asyncio.gather(return_exceptions=True)`` with a semaphore to
    limit concurrency. ``CancelledError`` still propagates.

    Args:
        coros: List of coroutines to execute.
        max_concurrency: Maximum number of concurrent tasks.

    Returns:
        List of results or exception objects, preserving input order.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run(coro: Coroutine[Any, Any, Any]) -> Any:
        async with semaphore:
            return await coro

    try:
        return await asyncio.gather(*[_run(c) for c in coros], return_exceptions=True)
    except asyncio.CancelledError:
        raise


async def gather_strict(
    coros: list[Coroutine[Any, Any, Any]],
    max_concurrency: int = 10,
) -> list[Any]:
    """Run coroutines concurrently with all-or-nothing semantics.

    Uses ``asyncio.TaskGroup`` for structured concurrency. If a single
    exception occurs it is unwrapped from the ``ExceptionGroup``.

    Args:
        coros: List of coroutines to execute.
        max_concurrency: Maximum number of concurrent tasks.

    Returns:
        List of results preserving input order.

    Raises:
        Exception: The single unwrapped exception when exactly one task fails.
        ExceptionGroup: When multiple tasks fail simultaneously.
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[Any] = [None] * len(coros)

    async def _run(index: int, coro: Coroutine[Any, Any, Any]) -> None:
        async with semaphore:
            results[index] = await coro

    try:
        async with asyncio.TaskGroup() as tg:
            for i, coro in enumerate(coros):
                tg.create_task(_run(i, coro))
    except ExceptionGroup as eg:
        if len(eg.exceptions) == 1:
            raise eg.exceptions[0] from eg
        raise

    return results
