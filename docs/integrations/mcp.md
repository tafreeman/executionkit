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

It recognizes MCP protocol versions `2024-11-05`, `2025-03-26`, and
`2025-06-18`, preferring `2025-06-18`.

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
