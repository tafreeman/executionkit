"""Human approval gate primitives."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from executionkit.errors import ExecutionKitError

ApprovalCallback: TypeAlias = Callable[["ApprovalRequest"], Any]


class ApprovalDeniedError(ExecutionKitError):
    """Raised when an approval-gated operation is denied."""


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
    """Async-compatible approval callback wrapper."""

    def __init__(self, callback: ApprovalCallback) -> None:
        self._callback = callback

    async def request(self, request: ApprovalRequest) -> ApprovalDecision:
        maybe_decision = self._callback(request)
        decision = (
            await maybe_decision
            if inspect.isawaitable(maybe_decision)
            else maybe_decision
        )
        if isinstance(decision, ApprovalDecision):
            return decision
        return ApprovalDecision(approved=bool(decision))

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
