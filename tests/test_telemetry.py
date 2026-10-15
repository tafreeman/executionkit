"""Tests for schema-v2 trace payloads and the TraceCollector.

Covers the study-telemetry contract:

* every ``llm_call_*`` event carries ``schema_version`` and a ``call_id``
  correlating all physical attempts of one logical call;
* per-call token counts are ``None`` — never fabricated zeros — when the
  provider reports no usage, on streaming calls included;
* retry attempts are individually identified and counted;
* budget refusals are distinguishable from provider failures;
* :class:`TraceCollector` builds per-call records from event payloads without
  ever reading the cumulative ``cost`` tracker snapshot.
"""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any

import pytest

from executionkit import (
    BudgetExhaustedError,
    CallRecord,
    CostTracker,
    LLMResponse,
    MockProvider,
    PermanentError,
    RateLimitError,
    RetryConfig,
    TokenUsage,
    ToolCall,
    TraceCollector,
    TraceEvent,
    checked_complete,
    checked_stream,
)
from executionkit.observability import TRACE_SCHEMA_VERSION

_NO_RETRY = RetryConfig(max_retries=0)


def _messages() -> list[dict[str, Any]]:
    return [{"role": "user", "content": "x"}]


def _usage(input_tokens: int, output_tokens: int) -> MappingProxyType[str, Any]:
    return MappingProxyType(
        {"input_tokens": input_tokens, "output_tokens": output_tokens}
    )


def _used_response(
    content: str = "hi",
    *,
    input_tokens: int = 3,
    output_tokens: int = 5,
    **kwargs: Any,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=_usage(input_tokens, output_tokens),
        **kwargs,
    )


class _ListTrace:
    """Minimal list-appending trace callback."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def __call__(self, event: TraceEvent) -> None:
        self.events.append(event)

    def by_kind(self, kind: str) -> list[TraceEvent]:
        return [event for event in self.events if event.kind == kind]


class _FlakyProvider:
    """Fails once with a retryable error, then succeeds with usage."""

    supports_tools = True

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: Any, **kwargs: Any) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            raise RateLimitError("slow down", retry_after=0.0)
        return _used_response("recovered", raw={"model": "served-after-retry"})


# ---------------------------------------------------------------------------
# checked_complete payload shape
# ---------------------------------------------------------------------------


async def test_checked_complete_emits_correlated_v2_events() -> None:
    provider = MockProvider(
        responses=[
            _used_response(
                raw={"model": "m-served"},
                finish_reason="tool_calls",
                tool_calls=(ToolCall(id="t1", name="search", arguments={"q": "x"}),),
            )
        ]
    )
    trace = _ListTrace()

    response = await checked_complete(
        provider,
        _messages(),
        CostTracker(),
        None,
        _NO_RETRY,
        trace,
        model="m-asked",
    )

    assert response.content == "hi"
    (start, end) = trace.by_kind("llm_call_start"), trace.by_kind("llm_call_end")
    assert len(start) == len(end) == 1

    start_payload = start[0].payload
    assert start_payload["schema_version"] == TRACE_SCHEMA_VERSION
    assert start_payload["attempt"] == 1
    assert start_payload["requested_model"] == "m-asked"
    assert isinstance(start_payload["started_at"], str)
    # ISO-8601 round-trip: a malformed timestamp fails to parse here.
    from datetime import datetime

    datetime.fromisoformat(start_payload["started_at"])

    end_payload = end[0].payload
    assert end_payload["schema_version"] == TRACE_SCHEMA_VERSION
    assert end_payload["call_id"] == start_payload["call_id"]
    assert end_payload["attempt_id"] == start_payload["attempt_id"]
    assert end_payload["attempts"] == 1
    assert end_payload["retry_count"] == 0
    assert end_payload["requested_model"] == "m-asked"
    assert end_payload["served_model"] == "m-served"
    assert end_payload["usage_reported"] is True
    assert end_payload["input_tokens"] == 3
    assert end_payload["output_tokens"] == 5
    assert end_payload["finish_reason"] == "tool_calls"
    assert end_payload["tool_calls"] == [{"name": "search"}]
    assert end_payload["duration_ms"] >= 0.0


async def test_checked_complete_marks_missing_usage_as_none_not_zero() -> None:
    # MockProvider turns a plain string into LLMResponse(content=...) with an
    # empty usage mapping — the "provider said nothing" case.
    trace = _ListTrace()
    await checked_complete(
        MockProvider(responses=["plain"]),
        _messages(),
        CostTracker(),
        None,
        _NO_RETRY,
        trace,
    )
    end_payload = trace.by_kind("llm_call_end")[0].payload
    assert end_payload["usage_reported"] is False
    assert end_payload["input_tokens"] is None
    assert end_payload["output_tokens"] is None
    assert end_payload["served_model"] is None


async def test_retry_attempts_share_call_id_with_distinct_attempt_ids() -> None:
    provider = _FlakyProvider()
    trace = _ListTrace()

    response = await checked_complete(
        provider,
        _messages(),
        CostTracker(),
        None,
        RetryConfig(max_retries=2, base_delay=0.0),
        trace,
    )

    assert response.content == "recovered"
    starts = trace.by_kind("llm_call_start")
    assert [event.payload["attempt"] for event in starts] == [1, 2]
    call_ids = {event.payload["call_id"] for event in starts}
    assert len(call_ids) == 1
    attempt_ids = [event.payload["attempt_id"] for event in starts]
    assert len(set(attempt_ids)) == 2

    end_payload = trace.by_kind("llm_call_end")[0].payload
    assert end_payload["attempts"] == 2
    assert end_payload["retry_count"] == 1
    assert end_payload["attempt_id"] == attempt_ids[-1]
    assert end_payload["served_model"] == "served-after-retry"


async def test_budget_refusal_is_distinguished_from_provider_failure() -> None:
    tracker = CostTracker()
    tracker.reserve_call()  # consume the single allowed call
    trace = _ListTrace()

    with pytest.raises(BudgetExhaustedError):
        await checked_complete(
            MockProvider(responses=["never used"]),
            _messages(),
            tracker,
            TokenUsage(llm_calls=1),
            _NO_RETRY,
            trace,
        )

    assert trace.by_kind("llm_call_start") == []
    (error,) = trace.by_kind("llm_call_error")
    assert error.payload["error_type"] == "BudgetExhaustedError"
    assert error.payload["budget_exhausted"] is True
    assert error.payload["attempts"] == 0


async def test_provider_failure_marks_budget_exhausted_false() -> None:
    trace = _ListTrace()
    with pytest.raises(PermanentError):
        await checked_complete(
            MockProvider(exception=PermanentError("nope")),
            _messages(),
            CostTracker(),
            None,
            _NO_RETRY,
            trace,
        )
    assert len(trace.by_kind("llm_call_start")) == 1
    (error,) = trace.by_kind("llm_call_error")
    assert error.payload["error_type"] == "PermanentError"
    assert error.payload["budget_exhausted"] is False
    assert error.payload["attempts"] == 1


# ---------------------------------------------------------------------------
# checked_stream payload shape
# ---------------------------------------------------------------------------


async def _drain(stream: Any) -> list[str]:
    return [delta async for delta in stream]


async def test_checked_stream_reports_usage_when_the_sink_provides_it() -> None:
    trace = _ListTrace()
    result = await checked_stream(
        MockProvider(responses=["hello"]),
        _messages(),
        CostTracker(),
        None,
        None,
        trace,
    )
    await _drain(result.text_stream)

    (start,) = trace.by_kind("llm_call_start")
    (end,) = trace.by_kind("llm_call_end")
    assert start.payload["streaming"] is True
    assert end.payload["streaming"] is True
    assert end.payload["call_id"] == start.payload["call_id"]
    assert end.payload["attempt_id"] == start.payload["attempt_id"]
    assert end.payload["usage_reported"] is True
    # MockProvider synthesizes a word-count usage for streamed responses.
    assert end.payload["output_tokens"] >= 1
    assert end.payload["duration_ms"] >= 0.0


async def test_checked_stream_marks_missing_usage_as_none_not_zero() -> None:
    trace = _ListTrace()
    result = await checked_stream(
        MockProvider(responses=[]),  # sink receives a usage-less response
        _messages(),
        CostTracker(),
        None,
        None,
        trace,
    )
    await _drain(result.text_stream)

    (end,) = trace.by_kind("llm_call_end")
    assert end.payload["usage_reported"] is False
    assert end.payload["input_tokens"] is None
    assert end.payload["output_tokens"] is None


async def test_checked_stream_budget_refusal_emits_error_before_any_start() -> None:
    tracker = CostTracker()
    tracker.reserve_call()
    trace = _ListTrace()

    with pytest.raises(BudgetExhaustedError):
        await checked_stream(
            MockProvider(responses=["never used"]),
            _messages(),
            tracker,
            TokenUsage(llm_calls=1),
            None,
            trace,
        )

    assert trace.by_kind("llm_call_start") == []
    (error,) = trace.by_kind("llm_call_error")
    assert error.payload["budget_exhausted"] is True
    assert error.payload["streaming"] is True
    assert error.payload["attempts"] == 0


# ---------------------------------------------------------------------------
# TraceCollector
# ---------------------------------------------------------------------------


async def test_collector_records_per_call_usage_not_cumulative_snapshots() -> None:
    # Two calls through one shared tracker: the cumulative "cost" snapshot in
    # the second end event already contains the first call's tokens.  The
    # collector must still attribute exactly 3/5 and 10/20 per call.
    tracker = CostTracker()
    collector = TraceCollector()
    provider = MockProvider(
        responses=[
            _used_response(input_tokens=3, output_tokens=5),
            _used_response(input_tokens=10, output_tokens=20),
        ]
    )
    for _ in range(2):
        await checked_complete(
            provider, _messages(), tracker, None, _NO_RETRY, collector
        )

    records = collector.records
    assert len(records) == 2
    assert (records[0].input_tokens, records[0].output_tokens) == (3, 5)
    assert (records[1].input_tokens, records[1].output_tokens) == (10, 20)
    assert all(record.ok for record in records)

    summary = collector.summary()
    assert summary["schema"] == "executionkit.telemetry.v1"
    assert summary["trace_schema_version"] == TRACE_SCHEMA_VERSION
    assert summary["calls"] == 2
    assert summary["succeeded"] == 2
    assert summary["failed"] == 0
    assert summary["usage"]["input_tokens"] == 13
    assert summary["usage"]["output_tokens"] == 25
    assert summary["usage"]["calls_missing_input_tokens"] == 0
    assert "cost" not in summary  # no rates supplied — no cost block at all
    json.dumps(summary)  # portable: must be JSON-serializable as-is


async def test_collector_summary_cost_only_with_rates() -> None:
    collector = TraceCollector()
    await checked_complete(
        MockProvider(responses=[_used_response()]),
        _messages(),
        CostTracker(),
        None,
        _NO_RETRY,
        collector,
    )
    summary = collector.summary(input_rate=1e-6, output_rate=2e-6)
    cost = summary["cost"]
    assert cost["covered_calls"] == 1
    assert cost["uncovered_calls"] == 0
    assert cost["cost_usd"] == pytest.approx(3e-6 + 5 * 2e-6)

    with pytest.raises(ValueError, match="together"):
        collector.summary(input_rate=1e-6)


async def test_collector_missing_usage_stays_uncounted() -> None:
    collector = TraceCollector()
    await checked_complete(
        MockProvider(responses=["plain"]),
        _messages(),
        CostTracker(),
        None,
        _NO_RETRY,
        collector,
    )
    (record,) = collector.records
    assert record.usage_reported is False
    assert record.input_tokens is None
    assert record.output_tokens is None

    summary = collector.summary(input_rate=1e-6, output_rate=1e-6)
    assert summary["usage"]["input_tokens"] is None
    assert summary["usage"]["calls_missing_input_tokens"] == 1
    # No covered call: cost is explicitly unknown, never 0.0.
    assert summary["cost"]["cost_usd"] is None
    assert summary["cost"]["uncovered_calls"] == 1


async def test_collector_tracks_retries_and_physical_attempts() -> None:
    collector = TraceCollector()
    await checked_complete(
        _FlakyProvider(),
        _messages(),
        CostTracker(),
        None,
        RetryConfig(max_retries=2, base_delay=0.0),
        collector,
    )
    (record,) = collector.records
    assert record.attempts == 2
    assert record.retry_count == 1
    assert len(record.attempt_ids) == 2
    assert record.served_model == "served-after-retry"

    summary = collector.summary()
    assert summary["attempts"] == 2
    assert summary["retries"] == 1


async def test_collector_records_budget_refusal_as_governance_outcome() -> None:
    tracker = CostTracker()
    tracker.reserve_call()
    collector = TraceCollector()
    with pytest.raises(BudgetExhaustedError):
        await checked_complete(
            MockProvider(responses=["never used"]),
            _messages(),
            tracker,
            TokenUsage(llm_calls=1),
            _NO_RETRY,
            collector,
        )
    (record,) = collector.records
    assert record.ok is False
    assert record.error_type == "BudgetExhaustedError"
    assert record.budget_exhausted is True

    summary = collector.summary()
    assert summary["failed"] == 1
    assert summary["budget_exhausted"] == 1


def test_collector_ignores_unversioned_and_unrelated_events() -> None:
    collector = TraceCollector()
    collector(TraceEvent.create("llm_call_end", {"input_tokens": 5}))
    collector(TraceEvent.create("checkpoint", {"step": 1}))
    assert collector.unversioned_events == 1
    assert collector.records == ()
    assert collector.summary()["unversioned_events_ignored"] == 1


async def test_collector_streaming_call() -> None:
    collector = TraceCollector()
    result = await checked_stream(
        MockProvider(responses=["hi"]),
        _messages(),
        CostTracker(),
        None,
        None,
        collector,
    )
    await _drain(result.text_stream)
    (record,) = collector.records
    assert record.streaming is True
    assert record.ok is True
    assert record.usage_reported is True
    assert collector.summary()["streaming_calls"] == 1


async def test_call_record_to_jsonable_round_trips() -> None:
    collector = TraceCollector()
    await checked_complete(
        MockProvider(responses=[_used_response(raw={"model": "m"})]),
        _messages(),
        CostTracker(),
        None,
        _NO_RETRY,
        collector,
        model="m",
    )
    (payload,) = collector.to_jsonable()
    decoded = json.loads(json.dumps(payload))
    assert decoded["requested_model"] == "m"
    assert decoded["served_model"] == "m"
    assert decoded["input_tokens"] == 3
    assert isinstance(decoded["attempt_ids"], list)

    record = CallRecord(
        call_id="c",
        attempts=1,
        attempt_ids=("a",),
        requested_model=None,
        served_model=None,
        started_at=None,
        duration_ms=None,
        usage_reported=False,
        input_tokens=None,
        output_tokens=None,
        retry_count=0,
        error_type=None,
        budget_exhausted=False,
        streaming=False,
        finish_reason=None,
        tool_call_names=(),
    )
    assert record.ok is True
    assert json.loads(json.dumps(record.to_jsonable()))["input_tokens"] is None
