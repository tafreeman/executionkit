"""Consumer contract: the private EK class agentic-runtime-platform imports.

ARP (github.com/tafreeman/agentic-runtime-platform) imports
``executionkit.patterns.base._TrackedProvider`` in
``agentic_v2/engine/ek_step_delegation.py`` and calls it with the shapes pinned
here. The class is private and no EK pattern uses it, so a rename, a signature
change or a dead-code cleanup would pass every other EK test and break ARP's EK
delegation path with no semver signal. These tests fail first and say why.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.cost import CostTracker

_WHY = (
    "agentic-runtime-platform imports executionkit.patterns.base._TrackedProvider "
    "(agentic_v2/engine/ek_step_delegation.py) and calls it with this shape. "
    "Changing it breaks ARP's EK delegation path: ship the change in a new minor "
    "version with a CHANGELOG entry, and update ARP in the same window."
)


def _tracked_provider_class() -> Any:
    module = importlib.import_module("executionkit.patterns.base")
    cls = getattr(module, "_TrackedProvider", None)
    if cls is None:
        pytest.fail(f"executionkit.patterns.base._TrackedProvider is gone. {_WHY}")
    return cls


def test_constructor_binds_arp_call_shape() -> None:
    cls = _tracked_provider_class()
    params = list(inspect.signature(cls.__init__).parameters)
    assert params[1:4] == ["provider", "tracker", "metadata"], (
        f"positional parameters changed to {params[1:4]}. {_WHY}"
    )
    try:
        inspect.signature(cls).bind(
            object(), object(), {}, budget=None, retry=None, context="step"
        )
    except TypeError as exc:
        pytest.fail(f"ARP's constructor call no longer binds: {exc}. {_WHY}")


def test_complete_binds_arp_call_shape() -> None:
    cls = _tracked_provider_class()
    assert inspect.iscoroutinefunction(cls.complete), (
        f"complete() is no longer a coroutine function; ARP awaits it. {_WHY}"
    )
    try:
        inspect.signature(cls.complete).bind(object(), [], max_tokens=1, tools=None)
    except TypeError as exc:
        pytest.fail(f"ARP's complete() call no longer binds: {exc}. {_WHY}")


async def test_arp_call_shape_returns_provider_response() -> None:
    """ARP's exact call: no EK call budget, default retry, max_tokens and tools."""
    cls = _tracked_provider_class()
    tracker = CostTracker()
    metadata: dict[str, Any] = {}
    tracked = cls(
        MockProvider(responses=["hello"]),
        tracker,
        metadata,
        budget=None,
        retry=None,
        context="step.complete_turn",
    )

    response = await tracked.complete(
        [{"role": "user", "content": "hi"}], max_tokens=16, tools=None
    )

    assert response.content == "hello", _WHY
    assert tracker.call_count == 1, _WHY
