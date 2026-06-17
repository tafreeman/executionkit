"""Structured observability hooks for ExecutionKit.

OTel integration
----------------
If ``opentelemetry-api`` is installed (``pip install executionkit[otel]``),
:func:`llm_span` wraps LLM calls in a real OpenTelemetry span.  When the
package is absent the function returns a no-op context manager so the call
path is identical — zero overhead, zero import error.
"""

from __future__ import annotations

import importlib.util as _importlib_util
import inspect
from collections.abc import Awaitable, Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

TraceCallback: TypeAlias = Callable[["TraceEvent"], Awaitable[None] | None]

# ---------------------------------------------------------------------------
# OpenTelemetry availability probe — evaluated once at module load time.
#
# We probe with importlib so that the flag is set without binding any
# module-level names that could be absent.  Each function that needs OTel
# does a local import inside ``if _OTEL_AVAILABLE`` to keep mypy --strict
# happy (no possibly-unbound names at the module level).
# ---------------------------------------------------------------------------

_OTEL_AVAILABLE: bool = _importlib_util.find_spec("opentelemetry") is not None

# ---------------------------------------------------------------------------
# Span name constant — centralised so tests and implementation stay in sync.
# ---------------------------------------------------------------------------

LLM_CALL_SPAN_NAME = "llm.call"

# ---------------------------------------------------------------------------
# TraceEvent / emit_trace — unchanged public API
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# OTel span helper
# ---------------------------------------------------------------------------


@contextmanager
def llm_span(model: str) -> Generator[Any, None, None]:
    """Context manager that wraps a single LLM call in an OTel span.

    When ``opentelemetry-api`` is **not** installed the context manager is a
    no-op — the yielded value is ``None`` and no tracing infrastructure is
    touched.  The call path is identical in both cases so code that checks
    for OTel availability lives only here.

    Usage::

        with llm_span(model) as span:
            response = await provider.complete(messages)
            record_llm_span_attributes(span, model, response)

    Args:
        model: The model identifier string (e.g. ``"gpt-4o"``).

    Yields:
        An OTel ``Span`` when the SDK is available, ``None`` otherwise.
    """
    if not _OTEL_AVAILABLE:
        yield None
        return

    # Local import: only reached when opentelemetry-api is installed.
    from opentelemetry import trace as otel_trace

    tracer = otel_trace.get_tracer("executionkit")
    with tracer.start_as_current_span(LLM_CALL_SPAN_NAME) as span:
        span.set_attribute("llm.model", model)
        yield span


def record_llm_span_attributes(
    span: Any,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float | None = None,
) -> None:
    """Set standard LLM attributes on an active OTel span.

    This is a no-op when *span* is ``None`` (OTel absent) or when the span
    is non-recording (e.g. a sampled-out or no-op span from the SDK).

    Attributes set:

    * ``llm.model`` — already set by :func:`llm_span`; repeated here for
      completeness if callers construct spans themselves.
    * ``llm.input_tokens`` — prompt / input token count.
    * ``llm.output_tokens`` — completion / output token count.
    * ``cost_usd`` — estimated dollar cost; **omitted** when ``None`` so we
      never emit a fabricated value when no rate table is available.

    Args:
        span: The span returned by the :func:`llm_span` context manager, or
            ``None`` when OTel is absent.
        model: Model identifier string.
        input_tokens: Number of input (prompt) tokens consumed.
        output_tokens: Number of output (completion) tokens produced.
        cost_usd: Optional pre-computed cost in USD.  Pass ``None`` to omit.
    """
    if span is None:
        return

    # Guard against non-recording spans (e.g. sampled-out spans from the SDK).
    # NonRecordingSpan.set_attribute is a no-op, but the is_recording() check
    # makes the intent explicit and avoids the attribute call entirely.
    if _OTEL_AVAILABLE:
        from opentelemetry.trace import NonRecordingSpan

        if isinstance(span, NonRecordingSpan):
            return

    span.set_attribute("llm.model", model)
    span.set_attribute("llm.input_tokens", input_tokens)
    span.set_attribute("llm.output_tokens", output_tokens)
    if cost_usd is not None:
        span.set_attribute("cost_usd", cost_usd)
