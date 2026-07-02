"""Entry point: ``python -m executionkit.mcp``.

Starts the stdio MCP server. Provider configuration is read from the
environment (``EXECUTIONKIT_BASE_URL``, ``EXECUTIONKIT_MODEL``,
``EXECUTIONKIT_API_KEY``); the server starts and answers ``initialize`` /
``tools/list`` even when those are unset, surfacing missing config only when a
tool is actually called.
"""

from __future__ import annotations

import asyncio
import contextlib

from executionkit.mcp.server import serve_stdio


def main() -> None:
    """Run the stdio MCP server until stdin reaches EOF."""
    # Ctrl-C / SIGINT is a normal way to stop a long-running stdio server.
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
