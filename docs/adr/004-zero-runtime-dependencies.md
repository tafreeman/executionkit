# ADR-004: Keep the base install dependency-free

- Status: Accepted
- Date: 2026-05-11
- Updated: 2026-07-28

## Context

Required HTTP, validation, and telemetry libraries increase installation size,
version conflicts, and security-maintenance work.

## Decision

Keep `project.dependencies` empty. Implement the base behavior with the Python
standard library and expose focused extras:

- `httpx` for the async HTTP transport;
- `jsonschema` for full tool-argument schema validation;
- `otel` for OpenTelemetry API support;
- `dev` and `docs` for contributor tooling.

## Consequences

- The base package can make requests through `urllib`.
- Optional capabilities must have a defined fallback or fail clearly.
- Code paths with and without each extra require tests.
- A new required dependency needs a new architecture decision.

## Rejected alternatives

Making the optional libraries required would simplify some code paths but
would remove the small base-install contract.
