# ADR-012: Stdlib-Only Stdio MCP Server Inside the Package

**Date:** 2026-07-02
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** Exposing ExecutionKit's reasoning patterns as Model Context Protocol (MCP) tools closes the library's largest named-primitive gap, but MCP support must not compromise the zero-runtime-dependency constraint (ADR-004) that defines the package.

---

## Context and Problem Statement

MCP is the emerging standard for exposing tools to LLM agents. ExecutionKit
consumes any OpenAI-compatible endpoint but, before this decision, offered no
way for an MCP client (Claude Desktop, Claude Code, or any MCP-speaking agent)
to invoke its patterns. The design had to answer three questions.

First, where does the MCP dependency boundary sit? The official `mcp` Python
SDK is the conventional implementation path, but ADR-004 forbids adding a
runtime dependency to the core package. Second, which transport and protocol
surface is in scope? MCP defines stdio and HTTP transports plus tools,
resources, prompts, and sampling capabilities. Third, what may MCP callers
execute? `react_loop` accepts arbitrary Python callables as tools when used as
a library, which is unacceptable to expose over a wire protocol.

## Decision Drivers

* ADR-004: the core package must gain **no** runtime dependency.
* MCP's stdio transport is newline-delimited JSON-RPC 2.0 — a surface the
  standard library (`json`, `asyncio`, `sys`) handles directly and correctly.
* The dispatch layer must be unit-testable in-process (no subprocess, no
  network) with an injectable provider, matching the repo's MockProvider
  testing convention.
* LLM output is untrusted (see the security documentation); an MCP endpoint
  must not become a remote-code-registration vector.
* A first-class module signals deliberate protocol support; an `examples/`
  script would signal a demo.

## Considered Options

* Option A: stdlib-only implementation inside the package (`executionkit/mcp/`)
* Option B: optional extra `executionkit[mcp]` depending on the official `mcp` SDK
* Option C: self-contained `examples/mcp_server/` package outside the library

## Decision Outcome

Chosen option: **Option A — stdlib-only `executionkit/mcp/`**, because the
stdio transport's actual protocol surface (line-delimited JSON-RPC 2.0, an
`initialize` handshake with protocol-version negotiation, `tools/list`,
`tools/call`, `ping`) is small enough to implement correctly with the standard
library, which keeps ADR-004 intact with no packaging split. Option B was
rejected because it forks the install story for a core capability and imports
a fast-moving SDK for a protocol subset the stdlib covers; Option C was
rejected because example code carries no compatibility promise and would
undercut the claim that MCP support is a supported feature.

Scope decisions that follow from the drivers:

* **Transport:** stdio only (`python -m executionkit.mcp`). No HTTP/SSE.
* **Capabilities:** `tools` only. `resources`, `prompts`, and `sampling` are
  intentionally not advertised.
* **Tools:** `consensus` and `react_loop`. `react_loop` is restricted to a
  fixed, side-effect-free demo toolset (calculator + echo) — MCP callers
  cannot register arbitrary Python callables. Lifting this requires a
  separately-reviewed allowlisting mechanism.
* **Provider wiring:** resolved from the same `EXECUTIONKIT_BASE_URL` /
  `EXECUTIONKIT_MODEL` / `EXECUTIONKIT_API_KEY` environment conventions as
  `live_provider_from_env()`. Missing configuration produces a structured
  `isError: true` tool result — the server starts and answers
  `initialize`/`tools/list` regardless, and never crashes on missing config.
* **Error model:** tool-level failures are MCP `isError` results; malformed
  frames and unknown methods return standard JSON-RPC error codes
  (`-32700`/`-32600`/`-32601`/`-32602`); unknown notifications are ignored
  silently per JSON-RPC.

### Consequences

* Good: zero new runtime dependencies; one install story; the protocol layer
  is a readable ~300-line module with named constants instead of an SDK
  black box.
* Good: the dispatch function is pure and in-process testable; the test suite
  covers the handshake, tool schemas, success and error paths, and a
  subprocess stdio round-trip.
* Bad: protocol-revision tracking is manual — future MCP spec revisions must
  be adopted by hand rather than via an SDK upgrade. Mitigated by the
  deliberately minimal advertised surface.
* Bad: no HTTP transport means remote MCP clients need a stdio bridge.
  Acceptable: the primary consumers (local agent runtimes) speak stdio.
