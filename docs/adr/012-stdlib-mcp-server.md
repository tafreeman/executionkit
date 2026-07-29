# ADR-012: Ship a small stdio MCP server

- Status: Accepted
- Date: 2026-07-02
- Updated: 2026-07-28

## Context

MCP clients need a way to invoke selected ExecutionKit behavior without adding
an MCP SDK to the base install.

## Decision

Implement JSON-RPC framing and MCP tool handling with the standard library over
standard input and output. Support protocol versions `2024-11-05`,
`2025-03-26`, and `2025-06-18`.

Expose four bounded tools:

- `consensus`, with 1 through 9 samples;
- `react_loop`, with 1 through 8 rounds;
- a fixed calculator; and
- a fixed echo tool.

The server reads provider configuration from environment variables. It does
not expose arbitrary Python callables or network transport.

## Consequences

- The server works with the base package.
- The small protocol surface can be audited and tested directly.
- New MCP methods and transports require explicit implementation.
- The demo tools are not a general tool registry.

## Rejected alternatives

An MCP SDK would reduce protocol code but add a required or integration-specific
dependency. Exposing arbitrary tools would create a larger execution boundary.
