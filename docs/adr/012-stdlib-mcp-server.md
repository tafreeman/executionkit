# ADR-012: Ship a small stdio MCP server

- Status: Accepted
- Date: 2026-07-02
- Updated: 2026-08-09

## Context

MCP clients need a way to invoke selected ExecutionKit behavior without adding
an MCP SDK to the base install.

## Decision

Implement JSON-RPC framing and MCP tool handling with the standard library over
standard input and output. Support the handshake-based protocol revisions
`2024-11-05`, `2025-03-26`, `2025-06-18`, and `2025-11-25`, preferring the
newest.

Stop at `2025-11-25`. That is the last revision built on the `initialize`
handshake, and its additions that could reach a tools-only stdio server are all
optional or gated behind client capabilities this server never requests, so
supporting it costs no new protocol code. Revision `2026-07-28` is a different
matter: it removes the handshake and the session, moves the protocol version
into per-request `_meta`, requires a `server/discover` RPC, and requires
`UnsupportedProtocolVersionError` (`-32022`) for an unsupported version.
Accepting that version string without that machinery would advertise a
capability the server does not have, which is worse than declining it. Adding
the handshake-free era is a separate decision and a separate record.

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
- Handshake-free clients are not locked out. The spec has them probe with
  `server/discover` and read any unrecognized error as a handshake-era server;
  this server returns such an error and gates `tools/call` behind `initialize`,
  giving the probe the deterministic answer it needs to fall back.
- Tracking the newest revision stays a code change, not a constant edit: the
  accepted set names only revisions whose requirements are met.

## Rejected alternatives

An MCP SDK would reduce protocol code but add a required or integration-specific
dependency. Exposing arbitrary tools would create a larger execution boundary.
