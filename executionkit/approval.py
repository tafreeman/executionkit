"""Human approval gate primitives."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, cast

from executionkit.errors import ExecutionKitError

ApprovalCallback: TypeAlias = Callable[["ApprovalRequest"], Any]


class ApprovalDeniedError(ExecutionKitError):
    """Raised when an approval-gated operation is denied."""


class ApprovalTimeoutError(ExecutionKitError):
    """Raised when an approval gate times out and on_timeout is ``"raise"``."""


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """A request to approve an operation before it runs."""

    action: str
    subject: str
    metadata: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    @classmethod
    def create(
        cls, action: str, subject: str, metadata: Mapping[str, Any] | None = None
    ) -> ApprovalRequest:
        return cls(
            action=action,
            subject=subject,
            metadata=MappingProxyType(dict(metadata or {})),
        )


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Approval result."""

    approved: bool
    reason: str = ""


class ApprovalGate:
    """Async-compatible approval callback wrapper.

    Parameters
    ----------
    callback:
        Synchronous or async callable that receives an :class:`ApprovalRequest`
        and returns an :class:`ApprovalDecision` (or a truthy/falsy value).
    timeout_seconds:
        If given, the callback must resolve within this many seconds.  When it
        does not, *on_timeout* controls the fallback behaviour.  ``None``
        (default) preserves the original blocking behaviour.
    on_timeout:
        What to do when *timeout_seconds* elapses before the callback resolves.

        * ``"raise"`` (default) — raise :class:`ApprovalTimeoutError`.
        * ``"approve"`` — treat the timed-out request as approved.
        * ``"deny"``   — treat the timed-out request as denied.
    """

    def __init__(
        self,
        callback: ApprovalCallback,
        *,
        timeout_seconds: float | None = None,
        on_timeout: Literal["approve", "deny", "raise"] = "raise",
    ) -> None:
        self._callback = callback
        self._timeout_seconds = timeout_seconds
        self._on_timeout = on_timeout

    async def request(self, request: ApprovalRequest) -> ApprovalDecision:
        awaitable = self._invoke(request)

        if self._timeout_seconds is None:
            decision = await awaitable
        else:
            try:
                decision = await asyncio.wait_for(
                    awaitable, timeout=self._timeout_seconds
                )
            except TimeoutError:
                return self._handle_timeout(request)

        if isinstance(decision, ApprovalDecision):
            return decision
        return ApprovalDecision(approved=bool(decision))

    def _invoke(self, request: ApprovalRequest) -> Awaitable[Any]:
        """Return an awaitable for the callback without blocking the event loop.

        Async callbacks are invoked directly (they yield control immediately).
        A synchronous callback may block (e.g. ``input()``); running it inline
        here would complete *before* ``wait_for`` is reached, silently defeating
        the timeout — so sync callbacks are dispatched to a worker thread.
        """
        if _is_async_callable(self._callback):
            return cast("Awaitable[Any]", self._callback(request))
        return asyncio.to_thread(self._callback, request)

    def _handle_timeout(self, request: ApprovalRequest) -> ApprovalDecision:
        """Apply the *on_timeout* policy after the wait deadline elapses."""
        if self._on_timeout == "approve":
            return ApprovalDecision(approved=True, reason="timed out — auto-approved")
        if self._on_timeout == "deny":
            return ApprovalDecision(approved=False, reason="timed out — auto-denied")
        raise ApprovalTimeoutError(
            f"Approval gate timed out after {self._timeout_seconds}s "
            f"for {request.action} {request.subject}"
        )

    async def require(self, request: ApprovalRequest) -> ApprovalDecision:
        decision = await self.request(request)
        if not decision.approved:
            reason = f": {decision.reason}" if decision.reason else ""
            raise ApprovalDeniedError(
                f"Approval denied for {request.action} {request.subject}{reason}"
            )
        return decision

    @classmethod
    def allow_all(cls) -> ApprovalGate:
        return cls(lambda request: ApprovalDecision(approved=True))

    @classmethod
    def deny_all(cls, reason: str = "denied") -> ApprovalGate:
        return cls(lambda request: ApprovalDecision(approved=False, reason=reason))


def _is_async_callable(callback: ApprovalCallback) -> bool:
    """True when *callback* (or its ``__call__``) is a coroutine function."""
    if inspect.iscoroutinefunction(callback):
        return True
    return inspect.iscoroutinefunction(type(callback).__call__)
