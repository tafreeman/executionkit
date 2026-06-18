# ADR-010: importlib Probe for Optional OpenTelemetry Integration

**Date:** 2026-06-18
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** The team wanted to emit OpenTelemetry spans around LLM calls when `opentelemetry-api` is installed, without adding a mandatory runtime dependency or scattering `try/except ImportError` guards throughout the codebase.

---

## Context and Problem Statement

ExecutionKit's zero-runtime-dependency constraint (ADR-004) prohibits
unconditional imports of any package that is not part of the Python standard
library. At the same time, users running OTel-instrumented services benefit
from having `llm.call` spans in their distributed traces without any extra
wrapper code.

The integration mechanism had to satisfy three properties simultaneously.
First, importing `executionkit.observability` must not raise `ImportError`
when `opentelemetry-api` is absent. Second, when OTel is present, spans must
be emitted with zero changes to call sites — the `llm_span` context manager
must work identically with or without the SDK. Third, the probe must be
evaluated once, not re-evaluated on every span entry, to keep the hot path
overhead negligible.

## Decision Drivers

* Zero runtime dependency — `opentelemetry-api` is an optional extra only.
* Call sites must be identical whether or not OTel is installed.
* The probe must not re-run on every `llm_span` call.
* `mypy --strict` must pass — no possibly-unbound module-level names.

## Considered Options

* Option A: `try/except ImportError` guard per call site
* Option B: `importlib.util.find_spec` probe at module load; local imports inside `if _OTEL_AVAILABLE`
* Option C: Separate opt-in module (`executionkit.otel`) that the caller imports explicitly

## Decision Outcome

**Chosen option:** Option B (`importlib.util.find_spec` probe at module load).

At the top of `executionkit/observability.py`, a single line probes for the
package without binding any module-level name:

```python
_OTEL_AVAILABLE: bool = importlib.util.find_spec("opentelemetry") is not None
```

`llm_span` is a `@contextmanager`. When `_OTEL_AVAILABLE` is `False` it yields
`None` immediately — a no-op. When `True`, it performs a local import of
`opentelemetry.trace` and starts a real span. The local import keeps
`mypy --strict` satisfied (no possibly-unbound names at module scope) and
means the OTel import machinery runs only for users who have the SDK installed.

```python
@contextmanager
def llm_span(model: str) -> Generator[Any, None, None]:
    if not _OTEL_AVAILABLE:
        yield None
        return

    from opentelemetry import trace as otel_trace  # local import
    tracer = otel_trace.get_tracer("executionkit")
    with tracer.start_as_current_span("llm.call") as span:
        span.set_attribute("llm.model", model)
        yield span
```

### Positive Consequences

* `importlib.util` is in the standard library — no new dependency.
* The probe runs once at module load; the hot path is a single boolean check.
* Call sites are identical: `with llm_span(model) as span:` works whether or
  not OTel is installed.
* `mypy --strict` is satisfied because OTel names only appear inside branches
  guarded by `_OTEL_AVAILABLE`.

### Negative Consequences

* `find_spec` probes at import time; if `opentelemetry` is installed after
  `executionkit.observability` is first imported (unusual in production but
  possible in some test setups), the flag will be stale. A process restart
  is required.

## Pros and Cons of the Options

### Option A: try/except ImportError per call site

* **Good:** Familiar Python idiom.
* **Bad:** Repeated boilerplate at every call site.
* **Bad:** `ImportError` is caught at runtime on every call rather than once
  at module load — unnecessary overhead.
* **Bad:** Scattered try/except blocks make it hard to audit which sites
  participate in OTel instrumentation.

### Option B: importlib.util.find_spec probe at module load

* **Good:** Single probe evaluated once; boolean check on the hot path.
* **Good:** All instrumented sites follow the same pattern — easy to audit.
* **Good:** Satisfies `mypy --strict` via local imports inside guarded branches.
* **Bad:** Stale flag if OTel is installed after the module is first imported.

### Option C: Separate opt-in module

* **Good:** Completely explicit — users import `executionkit.otel` to opt in.
* **Bad:** Requires callers to change their import paths when adding
  instrumentation, which is friction for gradual adoption.
* **Bad:** Patterns would need to import from a different module when OTel
  is desired, splitting the implementation.
