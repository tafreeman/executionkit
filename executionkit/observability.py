"""Structured observability hooks for ExecutionKit."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

TraceCallback: TypeAlias = Callable[["TraceEvent"], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """A structured event emitted by patterns and lightweight primitives."""

    kind: str
    payload: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    @classmethod
    def create(cls, kind: str, payload: Mapping[str, Any] | None = None) -> TraceEvent:
        return cls(kind=kind, payload=MappingProxyType(dict(payload or {})))


async def emit_trace(trace: TraceCallback | None, event: TraceEvent) -> None:
    """Emit *event* to an optional callback."""

    if trace is None:
        return
    maybe_awaitable = trace(event)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable
