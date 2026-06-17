"""Tests for executionkit.observability — OTel span instrumentation.

Two scenarios:
  (a) OTel absent (always runs): the call path still works, no error raised.
  (b) OTel SDK present (skipped when SDK not installed): an in-memory exporter
      captures the span and we assert the expected attributes are set.
"""

from __future__ import annotations

import importlib.util
from types import MappingProxyType
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.observability import (
    LLM_CALL_SPAN_NAME,
    TraceEvent,
    emit_trace,
    llm_span,
    record_llm_span_attributes,
)
from executionkit.provider import LLMResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESPONSE_WITH_USAGE = LLMResponse(
    content="hello",
    usage=MappingProxyType({"input_tokens": 10, "output_tokens": 20}),
)

# ---------------------------------------------------------------------------
# SDK availability probe (used for skipif markers and fixtures)
# ---------------------------------------------------------------------------

_SDK_AVAILABLE = importlib.util.find_spec("opentelemetry.sdk") is not None

# ---------------------------------------------------------------------------
# Shared OTel fixture — set the global TracerProvider ONCE per test session.
#
# The OTel SDK only allows set_tracer_provider() to be called once; subsequent
# calls are silently ignored.  We therefore configure a single TracerProvider
# with an InMemorySpanExporter at session scope, and clear the exporter
# between tests via a function-scoped fixture.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def otel_exporter() -> Any:
    """Session-scoped: install an InMemorySpanExporter into the global tracer."""
    if not _SDK_AVAILABLE:
        return None

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture()
def clean_spans(otel_exporter: Any) -> Any:
    """Function-scoped: clear the in-memory exporter before each test."""
    if otel_exporter is not None:
        otel_exporter.clear()
    return otel_exporter


# ---------------------------------------------------------------------------
# (a) No-op path — OTel absent (or disabled)
# ---------------------------------------------------------------------------


def test_llm_span_noop_when_otel_absent() -> None:
    """llm_span must be a no-op context manager when OTel is not installed."""
    import executionkit.observability as obs_module

    original = obs_module._OTEL_AVAILABLE
    try:
        obs_module._OTEL_AVAILABLE = False  # type: ignore[assignment]
        with llm_span("gpt-4o-mini") as span:
            assert span is None
    finally:
        obs_module._OTEL_AVAILABLE = original  # type: ignore[assignment]


def test_record_attributes_noop_when_span_is_none() -> None:
    """record_llm_span_attributes must not raise when span is None."""
    record_llm_span_attributes(None, "gpt-4o-mini", 10, 20)
    record_llm_span_attributes(None, "gpt-4o-mini", 10, 20, cost_usd=0.001)


async def test_mock_provider_complete_works_without_otel() -> None:
    """MockProvider.complete() must succeed end-to-end with OTel disabled."""
    import executionkit.observability as obs_module

    original = obs_module._OTEL_AVAILABLE
    try:
        obs_module._OTEL_AVAILABLE = False  # type: ignore[assignment]
        provider = MockProvider(responses=[_RESPONSE_WITH_USAGE])
        result = await provider.complete([{"role": "user", "content": "hi"}])
        assert result.content == "hello"
        assert result.input_tokens == 10
        assert result.output_tokens == 20
    finally:
        obs_module._OTEL_AVAILABLE = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# TraceEvent / emit_trace — existing public API (regression guard)
# ---------------------------------------------------------------------------


def test_trace_event_create() -> None:
    event = TraceEvent.create("llm.call", {"model": "gpt-4o"})
    assert event.kind == "llm.call"
    assert event.payload["model"] == "gpt-4o"


def test_trace_event_default_payload() -> None:
    event = TraceEvent.create("ping")
    assert event.payload == MappingProxyType({})


async def test_emit_trace_none_callback() -> None:
    """emit_trace must be a no-op when the callback is None."""
    event = TraceEvent.create("test")
    await emit_trace(None, event)  # must not raise


async def test_emit_trace_sync_callback() -> None:
    received: list[TraceEvent] = []

    def cb(e: TraceEvent) -> None:
        received.append(e)

    event = TraceEvent.create("test")
    await emit_trace(cb, event)
    assert received == [event]


async def test_emit_trace_async_callback() -> None:
    received: list[TraceEvent] = []

    async def cb(e: TraceEvent) -> None:
        received.append(e)

    event = TraceEvent.create("test")
    await emit_trace(cb, event)
    assert received == [event]


# ---------------------------------------------------------------------------
# (b) OTel SDK present — in-memory exporter assertions
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _SDK_AVAILABLE, reason="opentelemetry-sdk not installed")
def test_llm_span_emits_span_with_attributes(clean_spans: Any) -> None:
    """When OTel SDK is configured, llm_span emits a span with expected attrs."""
    with llm_span("test-model") as span:
        assert span is not None
        record_llm_span_attributes(span, "test-model", 10, 20)

    spans = clean_spans.get_finished_spans()
    assert len(spans) == 1
    finished = spans[0]
    assert finished.name == LLM_CALL_SPAN_NAME
    attrs = finished.attributes or {}
    assert attrs.get("llm.model") == "test-model"
    assert attrs.get("llm.input_tokens") == 10
    assert attrs.get("llm.output_tokens") == 20
    assert "cost_usd" not in attrs  # omitted when not passed


@pytest.mark.skipif(not _SDK_AVAILABLE, reason="opentelemetry-sdk not installed")
def test_llm_span_includes_cost_usd_when_provided(clean_spans: Any) -> None:
    """cost_usd attribute is emitted when explicitly supplied."""
    with llm_span("test-model") as span:
        assert span is not None
        record_llm_span_attributes(span, "test-model", 5, 15, cost_usd=0.0012)

    spans = clean_spans.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes or {}
    assert attrs.get("cost_usd") == pytest.approx(0.0012)


@pytest.mark.skipif(not _SDK_AVAILABLE, reason="opentelemetry-sdk not installed")
def test_llm_span_span_name_is_llm_call(clean_spans: Any) -> None:
    """Span name must be the LLM_CALL_SPAN_NAME constant."""
    with llm_span("any-model") as span:
        record_llm_span_attributes(span, "any-model", 1, 1)

    spans = clean_spans.get_finished_spans()
    assert spans[0].name == "llm.call"


@pytest.mark.skipif(not _SDK_AVAILABLE, reason="opentelemetry-sdk not installed")
def test_record_attributes_noop_on_non_recording_span() -> None:
    """record_llm_span_attributes must not raise on a non-recording span."""
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    ctx = SpanContext(
        trace_id=0x0,
        span_id=0x0,
        is_remote=False,
        trace_flags=TraceFlags(0),
    )
    non_recording = NonRecordingSpan(ctx)
    # Must not raise
    record_llm_span_attributes(non_recording, "model", 1, 1, cost_usd=0.001)
