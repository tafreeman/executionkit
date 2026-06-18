"""Tests for ApprovalGate timeout behaviour (EK-9).

Coverage:
- on_timeout="raise"  → ApprovalTimeoutError raised
- on_timeout="approve" → decision.approved is True
- on_timeout="deny"   → decision.approved is False
- no timeout (None)   → original blocking behaviour preserved
- sync callback       → still works with wait_for path
"""

from __future__ import annotations

import asyncio
import warnings

import pytest

from executionkit.approval import (
    ApprovalDecision,
    ApprovalDeniedError,
    ApprovalGate,
    ApprovalRequest,
    ApprovalTimeoutError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUEST = ApprovalRequest.create("delete", "file.txt")

# A tiny sleep longer than any timeout used below — guarantees "never resolves
# within the timeout window" without making tests slow.
_NEVER_RESOLVES_DELAY = 0.5


async def _pending_callback(request: ApprovalRequest) -> ApprovalDecision:
    """Async callback that never returns within the test window."""
    await asyncio.sleep(_NEVER_RESOLVES_DELAY)
    return ApprovalDecision(approved=True)  # unreachable in timeout tests


# ---------------------------------------------------------------------------
# Timeout → raise (default on_timeout)
# ---------------------------------------------------------------------------


async def test_timeout_raise_is_default() -> None:
    """When timeout elapses without on_timeout set, ApprovalTimeoutError is raised."""
    gate = ApprovalGate(_pending_callback, timeout_seconds=0.05)

    with pytest.raises(ApprovalTimeoutError) as exc_info:
        await gate.request(_REQUEST)

    assert "delete" in str(exc_info.value)
    assert "file.txt" in str(exc_info.value)
    assert "0.05" in str(exc_info.value)


async def test_timeout_raise_explicit() -> None:
    """on_timeout='raise' explicitly raises ApprovalTimeoutError."""
    gate = ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="raise")

    with pytest.raises(ApprovalTimeoutError):
        await gate.request(_REQUEST)


async def test_timeout_raise_propagates_through_require() -> None:
    """require() re-raises ApprovalTimeoutError (it is not an ApprovalDeniedError)."""
    gate = ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="raise")

    with pytest.raises(ApprovalTimeoutError):
        await gate.require(_REQUEST)


# ---------------------------------------------------------------------------
# Timeout → approve
# ---------------------------------------------------------------------------


async def test_timeout_approve_returns_approved_decision() -> None:
    """on_timeout='approve' returns an approved decision when deadline elapses."""
    gate = ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="approve")

    decision = await gate.request(_REQUEST)

    assert decision.approved is True
    assert "timed out" in decision.reason.lower()


async def test_timeout_approve_require_does_not_raise() -> None:
    """require() with on_timeout='approve' does not raise (decision is approved)."""
    gate = ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="approve")

    decision = await gate.require(_REQUEST)

    assert decision.approved is True


# ---------------------------------------------------------------------------
# Timeout → deny
# ---------------------------------------------------------------------------


async def test_timeout_deny_returns_denied_decision() -> None:
    """on_timeout='deny' returns a denied decision when deadline elapses."""
    gate = ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="deny")

    decision = await gate.request(_REQUEST)

    assert decision.approved is False
    assert "timed out" in decision.reason.lower()


async def test_timeout_deny_require_raises_approval_denied_error() -> None:
    """require() with on_timeout='deny' raises ApprovalDeniedError."""
    gate = ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="deny")

    with pytest.raises(ApprovalDeniedError):
        await gate.require(_REQUEST)


# ---------------------------------------------------------------------------
# No timeout (None) — original behaviour preserved
# ---------------------------------------------------------------------------


async def test_no_timeout_sync_callback_returns_decision() -> None:
    """With timeout_seconds=None (default) a sync callback works as before."""
    gate = ApprovalGate(lambda req: ApprovalDecision(approved=True))

    decision = await gate.request(_REQUEST)

    assert decision.approved is True


async def test_no_timeout_async_callback_returns_decision() -> None:
    """With timeout_seconds=None an async callback resolves normally."""

    async def callback(request: ApprovalRequest) -> ApprovalDecision:
        await asyncio.sleep(0)  # yield to event loop once
        return ApprovalDecision(approved=False, reason="manual deny")

    gate = ApprovalGate(callback)

    decision = await gate.request(_REQUEST)

    assert decision.approved is False
    assert decision.reason == "manual deny"


async def test_no_timeout_truthy_falsy_callback() -> None:
    """Truthy/falsy return values are coerced to ApprovalDecision as before."""
    approve_gate = ApprovalGate(lambda req: True)
    deny_gate = ApprovalGate(lambda req: False)

    assert (await approve_gate.request(_REQUEST)).approved is True
    assert (await deny_gate.request(_REQUEST)).approved is False


async def test_no_timeout_require_raises_on_deny() -> None:
    """require() still raises ApprovalDeniedError for denied decisions (no timeout)."""
    gate = ApprovalGate.deny_all("forbidden")

    with pytest.raises(ApprovalDeniedError, match="forbidden"):
        await gate.require(_REQUEST)


async def test_no_timeout_allow_all_shortcut() -> None:
    """allow_all() factory is unaffected by the new parameters."""
    gate = ApprovalGate.allow_all()
    decision = await gate.require(_REQUEST)
    assert decision.approved is True


# ---------------------------------------------------------------------------
# Sync callback with timeout (edge case: sync callbacks must still time out)
# ---------------------------------------------------------------------------


async def test_timeout_with_sync_callback_that_resolves_quickly() -> None:
    """A fast synchronous callback resolves before the timeout — no error raised."""
    gate = ApprovalGate(
        lambda req: ApprovalDecision(approved=True),
        timeout_seconds=1.0,
    )

    decision = await gate.request(_REQUEST)

    assert decision.approved is True


# ---------------------------------------------------------------------------
# Construction-time warning for on_timeout="approve" (fail-open guard)
# ---------------------------------------------------------------------------


def test_approve_on_timeout_emits_user_warning() -> None:
    """Constructing ApprovalGate with on_timeout='approve' must emit a UserWarning."""
    with pytest.warns(UserWarning, match="fail-open"):
        ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="approve")


def test_approve_on_timeout_warning_mentions_approve() -> None:
    """The warning text must reference 'approve' so callers know what triggered it."""
    with pytest.warns(UserWarning, match="approve"):
        ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="approve")


def test_approve_on_timeout_warning_mentions_privilege() -> None:
    """The warning text must mention the security/privilege risk."""
    with pytest.warns(UserWarning, match="privilege"):
        ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="approve")


def test_no_warning_for_default_on_timeout() -> None:
    """Default construction (on_timeout='raise') must NOT emit any UserWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        # Should not raise; if a UserWarning were emitted it would become an error.
        ApprovalGate(_pending_callback, timeout_seconds=0.05)


def test_no_warning_for_raise_on_timeout() -> None:
    """Explicit on_timeout='raise' must NOT emit any UserWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="raise")


def test_no_warning_for_deny_on_timeout() -> None:
    """on_timeout='deny' must NOT emit any UserWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        ApprovalGate(_pending_callback, timeout_seconds=0.05, on_timeout="deny")
