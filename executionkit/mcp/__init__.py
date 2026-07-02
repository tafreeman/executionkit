"""Stdlib-only Model Context Protocol (MCP) server for ExecutionKit.

Exposes ExecutionKit reasoning patterns (:func:`~executionkit.consensus` and
:func:`~executionkit.react_loop`) as MCP *tools* over the stdio transport —
newline-delimited JSON-RPC 2.0 messages on stdin/stdout, UTF-8.

The server is implemented with the Python standard library only (``json``,
``asyncio``, ``sys``); it adds **no** runtime dependency to the ``executionkit``
package, preserving the zero-runtime-dependency constraint (ADR-004, ADR-012).

Run it as a module::

    python -m executionkit.mcp

Only the ``tools`` capability is advertised. ``resources``, ``prompts``, and
``sampling`` are intentionally out of scope.
"""

from __future__ import annotations

from executionkit.mcp.server import MCPServer, handle_message, serve_stdio

__all__ = [
    "MCPServer",
    "handle_message",
    "serve_stdio",
]
