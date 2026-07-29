# ADR-010: Probe once for optional OpenTelemetry support

- Status: Accepted
- Date: 2026-06-18

## Context

LLM calls should emit spans when OpenTelemetry is installed without making it
a base dependency or scattering import handling across call sites.

## Decision

At module import, use `importlib.util.find_spec()` to record whether the
OpenTelemetry API is available. `llm_span()` imports it locally only on the
enabled path; otherwise it yields a no-op context.

Span attributes include the model and returned token counts. A monetary cost
attribute is emitted only when the caller supplies one.

## Consequences

- Call sites use one context-manager path with or without the extra.
- Installing the package after `executionkit.observability` is already imported
  requires a process restart or module reload.
- The API package alone does not configure exporters, sampling, or storage.
- No price is invented when the caller has not supplied one.

## Rejected alternatives

Per-call import guards duplicate policy. A required telemetry dependency would
violate the base-install decision.
