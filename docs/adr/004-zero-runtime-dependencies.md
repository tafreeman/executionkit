# ADR-004: Zero Runtime Dependencies

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** During the v0.1 scope review, the team fixed `dependencies = []` in `pyproject.toml` as an explicit architectural constraint, making the single optional extra (`httpx`) an opt-in transport backend rather than a required install.

---

## Context and Problem Statement

LLM toolkits commonly bundle HTTP clients, retry libraries, schema validators, and serialisation frameworks as required runtime dependencies. Each bundled dependency expands the install footprint, introduces transitive conflicts, and requires the library maintainer to track security advisories and version pins for packages the user may already have at a different version.

ExecutionKit's value proposition is composable reasoning patterns and budget-aware execution — not HTTP transport, schema validation, or observability plumbing. The team needed to decide how many runtime dependencies were acceptable at v0.1 and where the boundary should sit.

## Decision Drivers

* Installing `executionkit` must not force users to pull in packages they neither want nor control.
* The library's identity is reasoning patterns over an existing LLM client — it should compose with the user's stack, not replace it.
* Runtime dependency audits (`pip-audit`) run in CI on every push; a zero-dep base makes audits fast and keeps the attack surface minimal.
* The `LLMProvider` structural protocol already hands HTTP transport responsibility to the caller; the library does not own the network layer.

## Considered Options

* Option A: Zero runtime dependencies; `httpx` as an optional extra only
* Option B: Bundle `httpx` as a required dependency for connection pooling
* Option C: Bundle `httpx` plus `jsonschema` for tool-argument validation

## Decision Outcome

**Chosen option:** Option A (zero runtime dependencies), because the standard library (`urllib.request`, `json`, `asyncio`) covers all required functionality. `httpx` is offered as an optional install (`pip install executionkit[httpx]`) for users who want connection pooling; the `Provider` class detects its presence at import time and substitutes it for `urllib` transparently. JSON Schema validation for tool arguments in `react_loop` is implemented using the standard library only.

### Positive Consequences

* `pip install executionkit` pulls in no transitive packages.
* `pip-audit` in CI has nothing to scan on the base install, keeping the security surface minimal.
* Users with existing `httpx` installs get connection pooling at no extra cost; users without it get a working implementation using `urllib`.
* The library can be embedded in environments with strict dependency controls (enterprise proxies, air-gapped systems) without negotiation.

### Negative Consequences

* The stdlib `urllib` transport lacks connection pooling, which matters for high-throughput `consensus` calls with large `num_samples`. Users in that scenario must opt into `httpx`.
* Tool-argument JSON Schema validation (`_validate_tool_args` in `react_loop`) supports a practical subset of JSON Schema (required fields, `additionalProperties`, and type checks) rather than the full specification. Full validation would require `jsonschema`.

## Pros and Cons of the Options

### Option A: Zero runtime deps; `httpx` optional

* **Good:** No install-time conflicts; composable with any Python environment.
* **Good:** Minimal security audit surface.
* **Good:** Consistent with the library's identity as a pattern library, not a client framework.
* **Bad:** stdlib transport has no connection pooling; high-concurrency patterns benefit from `httpx`.

### Option B: `httpx` required

* **Good:** Connection pooling available out of the box for all users.
* **Bad:** Forces an `httpx` pin on users who already have it at a different version, or who do not need pooling.
* **Bad:** Contradicts the zero-dependency positioning.

### Option C: `httpx` + `jsonschema` required

* **Good:** Full JSON Schema validation for tool arguments.
* **Bad:** Further expands the required install; `jsonschema` itself has transitive dependencies.
* **Bad:** The full JSON Schema specification is far beyond what tool-argument validation needs in practice.
