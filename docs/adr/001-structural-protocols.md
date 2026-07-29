# ADR-001: Use structural provider protocols

- Status: Accepted
- Date: 2026-05-11

## Context

Patterns must accept the built-in HTTP provider, custom providers, and test
doubles without requiring them to inherit from an ExecutionKit class.

## Decision

Define `LLMProvider`, `ToolCallingProvider`, and `StreamingProvider` with
`typing.Protocol`. Capability-specific protocols add only the methods or
markers needed for that capability.

## Consequences

- A compatible object works through structural typing.
- Tests can use small fakes without a base class.
- Runtime protocol checks verify attribute shape, not full behavior.
- Wrappers must report tool and streaming support truthfully.

## Rejected alternative

Abstract base classes would make inheritance mandatory and couple external
implementations to this package without adding a useful runtime guarantee.
