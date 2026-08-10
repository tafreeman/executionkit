# MCP server

ExecutionKit includes a small Model Context Protocol server implemented with
the Python standard library.

## Start it

Configure the backing OpenAI-compatible endpoint:

=== "macOS or Linux"

    ```bash
    export EXECUTIONKIT_BASE_URL="http://localhost:11434/v1"
    export EXECUTIONKIT_MODEL="<installed-model>"
    export EXECUTIONKIT_API_KEY=""
    python -m executionkit.mcp
    ```

=== "PowerShell"

    ```powershell
    $env:EXECUTIONKIT_BASE_URL = "http://localhost:11434/v1"
    $env:EXECUTIONKIT_MODEL = "<installed-model>"
    $env:EXECUTIONKIT_API_KEY = ""
    python -m executionkit.mcp
    ```

The process reads newline-delimited JSON-RPC 2.0 from standard input and writes
responses to standard output. Configure an MCP client to launch the command;
do not type interactive prompts into the process.

The server can start without provider variables. `initialize` and `tools/list`
still work, while `tools/call` returns a structured error explaining the
missing configuration.

## Exposed tools

| Tool | Inputs | Limits |
|---|---|---|
| `consensus` | `prompt`, optional `n`, `strategy`, `temperature` | `n` is clamped to 1 through 9. |
| `react_loop` | `prompt`, optional `max_rounds` | Rounds are clamped to 1 through 8. Tools inside the loop are fixed. |

The MCP `react_loop` can use only the built-in calculator and echo tools. MCP
callers cannot register Python functions.

The calculator parses arithmetic with an AST allowlist. It does not call
`eval()`.

## Protocol scope

The server supports the `tools` capability over stdio. It does not advertise:

- resources;
- prompts;
- sampling;
- HTTP, SSE, or Streamable HTTP transport; or
- caller-defined tool registration.

### Protocol revisions

It recognizes MCP protocol revisions `2024-11-05`, `2025-03-26`, `2025-06-18`,
and `2025-11-25`, preferring `2025-11-25`. A client that proposes one of those
gets it echoed back; any other proposal is answered with `2025-11-25`.

These are the handshake-based revisions — the ones built on `initialize` plus
`notifications/initialized`. `2025-11-25` is the newest of them, and everything
it added that could reach a tools-only stdio server is optional or gated behind
a client capability this server never requests, so it is implemented rather
than merely claimed.

The server does **not** implement revision `2026-07-28` or later. That revision
removed the handshake and the session: each request carries its own version in
`_meta`, servers must implement a `server/discover` RPC, and an unsupported
version must be rejected with `UnsupportedProtocolVersionError` (`-32022`).
None of that is implemented here, so `2026-07-28` is deliberately absent from
the accepted set — advertising it would be a false capability claim.

A `2026-07-28` client still interoperates safely. The spec has such clients
probe with `server/discover` and treat any unrecognized error as proof of a
handshake-era server; this server answers that probe with a JSON-RPC error and
refuses `tools/call` until `initialize` has succeeded, which is exactly the
deterministic signal the probe expects before it falls back to `initialize`.

JSON-RPC parse, request, method, and parameter errors use the standard error
codes. Tool execution failures use MCP tool results with `isError: true`.

## Client configuration shape

MCP clients use different configuration files, but the process definition has
this general shape:

```json
{
  "command": "python",
  "args": ["-m", "executionkit.mcp"],
  "env": {
    "EXECUTIONKIT_BASE_URL": "http://localhost:11434/v1",
    "EXECUTIONKIT_MODEL": "<installed-model>",
    "EXECUTIONKIT_API_KEY": ""
  }
}
```

Use the Python executable from the environment where ExecutionKit is
installed.

## Security boundary

The server intentionally exposes a smaller surface than the library API:

- no remote transport is opened;
- no arbitrary Python tool is accepted over the protocol;
- numeric tool arguments are bounded;
- provider configuration comes from the server process environment; and
- missing configuration becomes a tool error rather than a crash.

The backing model still receives prompts supplied by the MCP client. Apply
normal endpoint access controls and logging rules.

## Related

- [ADR-012](../adr/012-stdlib-mcp-server.md)
- [Provider setup](../getting-started/providers.md)
- [Security](../security.md)
