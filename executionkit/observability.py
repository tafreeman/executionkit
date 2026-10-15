"""Structured observability hooks for ExecutionKit.

OTel integration
----------------
If ``opentelemetry-api`` is installed (``pip install executionkit[otel]``),
:func:`llm_span` wraps LLM calls in a real OpenTelemetry span.  When the
package is absent, the function returns a no-op context manager and does not
import OpenTelemetry.

Trace payload schema
--------------------
:func:`~executionkit.patterns.base.checked_complete` and
:func:`~executionkit.patterns.base.checked_stream` emit three event kinds —
``llm_call_start`` (once per *physical* attempt, including retries),
``llm_call_end`` (once per *logical* call, after the final attempt succeeds),
and ``llm_call_error`` (once per logical call that failed or was refused by
the budget gate).  Payloads are versioned by ``schema_version``; the current
version is :data:`TRACE_SCHEMA_VERSION`.

Version 2 payloads are additive over the original keys and carry:

* ``schema_version`` (``int``) — payload schema; always
  :data:`TRACE_SCHEMA_VERSION` on newly emitted events.
* ``call_id`` (``str``) — correlation id shared by every event of one
  logical call (all retry attempts join on it).
* ``attempt_id`` (``str``) — unique id of one physical attempt; present on
  ``llm_call_start`` and on the terminal ``llm_call_end`` (the attempt that
  produced the response).
* ``attempt`` (``int``) — 1-based attempt number (start events).
* ``attempts`` (``int``) — total physical attempts made (end/error events).
* ``retry_count`` (``int``) — ``attempts - 1`` (end events).
* ``requested_model`` (``str | None``) — the ``model=`` kwarg the caller
  asked for, or ``None`` when the provider default applied.
* ``served_model`` (``str | None``) — the model the provider reports having
  used, when the raw payload carries one (end events).
* ``started_at`` (``str``) — ISO-8601 UTC dispatch timestamp.
* ``duration_ms`` (``float``) — wall duration of the whole logical call,
  retries included (end/error events).
* ``usage_reported`` (``bool``) — whether the provider returned a usage
  object at all (end events).
* ``input_tokens`` / ``output_tokens`` (``int | None``) — per-call counts;
  ``None``, **never** a fabricated ``0``, for the half the provider omitted.
* ``finish_reason`` (``str``) and ``tool_calls`` (``list[{"name": str}]``) —
  end events.
* ``error_type`` (``str``) and ``budget_exhausted`` (``bool``) — error
  events; ``budget_exhausted`` distinguishes a budget refusal from a
  provider failure.
* ``streaming`` (``bool``) — present and ``True`` on stream events.
* ``cost`` — cumulative :class:`~executionkit.types.TokenUsage` tracker
  snapshot at emit time.  This is a *running total*, not a per-call cost:
  never sum these snapshots across events (each one re-counts every earlier
  call).  Per-call usage comes from the ``input_tokens``/``output_tokens``
  keys above.
* ``content`` — the redacted completion text (end events).
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
# Trace payload schema version.  History:
#   1 — the original payloads (kind, attempt, cost, content, error_type).
#   2 — adds correlation ids, timestamps/duration, requested/served model,
#       retry and budget outcomes, and explicit missing-usage markers.
# See the module docstring for the full version-2 key list.
# ---------------------------------------------------------------------------
TRACE_SCHEMA_VERSION: int = 2

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
    """A structured event emitted during pattern and coordination calls."""

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

    # Skip non-recording spans (sampled-out / no-op). ``is_recording()`` is the
    # public OTel API and avoids importing SDK-internal span classes — which
    # also keeps this module import-clean when opentelemetry is not installed.
    if hasattr(span, "is_recording") and not span.is_recording():
        return

    span.set_attribute("llm.model", model)
    span.set_attribute("llm.input_tokens", input_tokens)
    span.set_attribute("llm.output_tokens", output_tokens)
    if cost_usd is not None:
        span.set_attribute("cost_usd", cost_usd)
