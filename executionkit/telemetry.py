"""Per-call telemetry collected from schema-v2 trace events.

:class:`TraceCollector` is a :data:`~executionkit.observability.TraceCallback`
that joins the ``llm_call_start`` / ``llm_call_end`` / ``llm_call_error``
events emitted by
:func:`~executionkit.patterns.base.checked_complete` and
:func:`~executionkit.patterns.base.checked_stream` into one
:class:`CallRecord` per *logical* call, and renders a portable, JSON-safe
:meth:`~TraceCollector.summary` of a run.

Two accounting rules are load-bearing:

* **Per-call usage comes from the end event's own token keys, never from the
  cumulative ``cost`` snapshot.**  The ``cost`` payload is a running total of
  the shared :class:`~executionkit.cost.CostTracker`; summing those snapshots
  across events re-counts every earlier call.  The collector never reads it.
* **Missing usage stays missing.**  A provider that returned no usage object
  yields ``None`` token counts and inflates the ``missing`` tallies — it is
  never recorded as zero, so a summary can never mistake "unmeasured" for
  "free".

The module has no opinion about downstream consumers.  ``to_jsonable()`` and
``summary()`` emit plain JSON-safe structures with stable key names so a
harness (an eval runner, a study driver, an orchestrator step) can map them
onto whatever telemetry envelope it speaks without ExecutionKit importing
that harness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from executionkit.observability import TRACE_SCHEMA_VERSION, TraceEvent

#: Schema tag carried in every portable summary, so a consumer can detect a
#: shape change before parsing fields it does not recognise.
TELEMETRY_SUMMARY_SCHEMA: Final[str] = "executionkit.telemetry.v1"

_LLM_EVENT_KINDS: Final[frozenset[str]] = frozenset(
    {"llm_call_start", "llm_call_end", "llm_call_error"}
)


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One logical LLM call reconstructed from correlated trace events.

    ``None`` always means "not observed / not reported" — counts are never
    back-filled with zero.  ``attempt_ids`` preserves one id per physical
    attempt (retries included) in dispatch order.
    """

    call_id: str
    attempts: int
    attempt_ids: tuple[str, ...]
    requested_model: str | None
    served_model: str | None
    started_at: str | None
    duration_ms: float | None
    usage_reported: bool
    input_tokens: int | None
    output_tokens: int | None
    retry_count: int
    error_type: str | None
    budget_exhausted: bool
    streaming: bool
    finish_reason: str | None
    tool_call_names: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """``True`` when the call produced a response (no terminal error)."""
        return self.error_type is None

    def to_jsonable(self) -> dict[str, Any]:
        """Return a JSON-safe dict; ``None`` markers are preserved as null."""
        return {
            "call_id": self.call_id,
            "attempts": self.attempts,
            "attempt_ids": list(self.attempt_ids),
            "requested_model": self.requested_model,
            "served_model": self.served_model,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "usage_reported": self.usage_reported,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "retry_count": self.retry_count,
            "error_type": self.error_type,
            "budget_exhausted": self.budget_exhausted,
            "streaming": self.streaming,
            "finish_reason": self.finish_reason,
            "tool_call_names": list(self.tool_call_names),
        }


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _new_entry() -> dict[str, Any]:
    return {
        "attempt_ids": [],
        "attempts": 0,
        "requested_model": None,
        "started_at": None,
        "streaming": False,
    }


class TraceCollector:
    """A trace callback that accumulates :class:`CallRecord` entries.

    Attach it as the ``trace=`` argument of any pattern (or of
    :func:`~executionkit.patterns.base.checked_complete` directly); it is
    synchronous and never raises on malformed events — events outside the
    schema-v2 ``llm_call_*`` contract are counted under
    :attr:`unversioned_events` and skipped.

    Not thread-safe, matching the library's cooperative-asyncio concurrency
    model (see :mod:`executionkit.cost`).
    """

    def __init__(self) -> None:
        self._open: dict[str, dict[str, Any]] = {}
        self._records: list[CallRecord] = []
        self._unversioned_events = 0

    @property
    def unversioned_events(self) -> int:
        """Count of ``llm_call_*`` events ignored for lacking v2 correlation."""
        return self._unversioned_events

    @property
    def records(self) -> tuple[CallRecord, ...]:
        """Finalized call records in completion order."""
        return tuple(self._records)

    def __call__(self, event: TraceEvent) -> None:
        """Consume one trace event; safe to use directly as ``trace=``."""
        if event.kind not in _LLM_EVENT_KINDS:
            return
        payload = event.payload
        call_id = payload.get("call_id")
        if payload.get("schema_version") != TRACE_SCHEMA_VERSION or not isinstance(
            call_id, str
        ):
            self._unversioned_events += 1
            return
        if event.kind == "llm_call_start":
            self._on_start(call_id, payload)
            return
        self._finalize(call_id, payload, failed=event.kind == "llm_call_error")

    def _on_start(self, call_id: str, payload: Any) -> None:
        entry = self._open.setdefault(call_id, _new_entry())
        attempt_id = payload.get("attempt_id")
        if isinstance(attempt_id, str) and attempt_id:
            entry["attempt_ids"].append(attempt_id)
        attempt = _optional_int(payload.get("attempt"))
        if attempt is not None and attempt > entry["attempts"]:
            entry["attempts"] = attempt
        if entry["requested_model"] is None:
            entry["requested_model"] = _optional_str(payload.get("requested_model"))
        if entry["started_at"] is None:
            entry["started_at"] = _optional_str(payload.get("started_at"))
        entry["streaming"] = entry["streaming"] or bool(payload.get("streaming"))

    def _finalize(self, call_id: str, payload: Any, *, failed: bool) -> None:
        # An end/error event can arrive with no matching start when the
        # collector was attached mid-flight; record what the payload carries
        # rather than dropping the call.
        entry = self._open.pop(call_id, _new_entry())
        payload_attempts = _optional_int(payload.get("attempts"))
        attempts = (
            payload_attempts if payload_attempts is not None else entry["attempts"]
        )
        attempt_id = _optional_str(payload.get("attempt_id"))
        attempt_ids: list[str] = list(entry["attempt_ids"])
        if attempt_id is not None and attempt_id not in attempt_ids:
            attempt_ids.append(attempt_id)
        payload_retry_count = _optional_int(payload.get("retry_count"))
        requested = _optional_str(payload.get("requested_model"))
        started_at = _optional_str(payload.get("started_at"))
        tool_calls = payload.get("tool_calls")
        tool_call_names = (
            tuple(
                name
                for call in tool_calls
                if isinstance(call, dict)
                and isinstance((name := call.get("name")), str)
                and name
            )
            if isinstance(tool_calls, list)
            else ()
        )
        self._records.append(
            CallRecord(
                call_id=call_id,
                attempts=attempts,
                attempt_ids=tuple(attempt_ids),
                requested_model=(
                    requested if requested is not None else entry["requested_model"]
                ),
                served_model=_optional_str(payload.get("served_model")),
                started_at=(
                    started_at if started_at is not None else entry["started_at"]
                ),
                duration_ms=_optional_float(payload.get("duration_ms")),
                usage_reported=bool(payload.get("usage_reported", False)),
                input_tokens=_optional_int(payload.get("input_tokens")),
                output_tokens=_optional_int(payload.get("output_tokens")),
                retry_count=(
                    payload_retry_count
                    if payload_retry_count is not None
                    else max(attempts - 1, 0)
                ),
                error_type=(
                    _optional_str(payload.get("error_type")) if failed else None
                ),
                budget_exhausted=bool(payload.get("budget_exhausted", False)),
                streaming=bool(payload.get("streaming", False)) or entry["streaming"],
                finish_reason=_optional_str(payload.get("finish_reason")),
                tool_call_names=tool_call_names,
            )
        )

    def to_jsonable(self) -> list[dict[str, Any]]:
        """Return all finalized records as JSON-safe dicts."""
        return [record.to_jsonable() for record in self._records]

    def summary(
        self,
        *,
        input_rate: float | None = None,
        output_rate: float | None = None,
    ) -> dict[str, Any]:
        """Return a portable, JSON-safe aggregate of the collected calls.

        Token and cost totals cover **only calls whose provider reported
        usage**; the ``*_missing`` counts say how much of the run the totals
        do *not* cover.  Cost is computed only when both per-token rates are
        supplied — ExecutionKit ships no price table — and is ``None`` when
        no covered call exists, never a fabricated ``0.0``.

        Args:
            input_rate: Optional cost per input token (e.g. ``3e-6``).
            output_rate: Optional cost per output token.

        Returns:
            A dict tagged with ``executionkit.telemetry.v1`` whose values are
            JSON-safe (tuples rendered as lists, missing data as ``None``).

        Raises:
            ValueError: If exactly one rate is supplied.
        """
        if (input_rate is None) != (output_rate is None):
            raise ValueError(
                "input_rate and output_rate must be supplied together or not at all"
            )
        records = self._records
        input_values = [r.input_tokens for r in records if r.input_tokens is not None]
        output_values = [
            r.output_tokens for r in records if r.output_tokens is not None
        ]
        durations = [r.duration_ms for r in records if r.duration_ms is not None]
        requested = sorted(
            model for model in {r.requested_model for r in records} if model is not None
        )
        served = sorted(
            model for model in {r.served_model for r in records} if model is not None
        )

        result: dict[str, Any] = {
            "schema": TELEMETRY_SUMMARY_SCHEMA,
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "calls": len(records),
            "succeeded": sum(1 for r in records if r.ok),
            "failed": sum(1 for r in records if not r.ok),
            "budget_exhausted": sum(1 for r in records if r.budget_exhausted),
            "attempts": sum(r.attempts for r in records),
            "retries": sum(r.retry_count for r in records),
            "streaming_calls": sum(1 for r in records if r.streaming),
            "tool_calls": sum(len(r.tool_call_names) for r in records),
            "usage": {
                "input_tokens": sum(input_values) if input_values else None,
                "output_tokens": sum(output_values) if output_values else None,
                "calls_with_input_tokens": len(input_values),
                "calls_missing_input_tokens": len(records) - len(input_values),
                "calls_with_output_tokens": len(output_values),
                "calls_missing_output_tokens": len(records) - len(output_values),
            },
            "latency_ms": (
                {
                    "count": len(durations),
                    "sum": sum(durations),
                    "mean": sum(durations) / len(durations),
                    "max": max(durations),
                }
                if durations
                else None
            ),
            "models": {
                "requested": requested,
                "served": served,
                "unattributed_calls": sum(
                    1
                    for r in records
                    if r.requested_model is None and r.served_model is None
                ),
            },
            "unversioned_events_ignored": self._unversioned_events,
        }
        if input_rate is not None and output_rate is not None:
            covered = [
                r
                for r in records
                if r.input_tokens is not None and r.output_tokens is not None
            ]
            covered_input = sum(
                r.input_tokens for r in covered if r.input_tokens is not None
            )
            covered_output = sum(
                r.output_tokens for r in covered if r.output_tokens is not None
            )
            result["cost"] = {
                "input_rate": input_rate,
                "output_rate": output_rate,
                "covered_calls": len(covered),
                "uncovered_calls": len(records) - len(covered),
                "cost_usd": (
                    covered_input * input_rate + covered_output * output_rate
                    if covered
                    else None
                ),
            }
        return result
