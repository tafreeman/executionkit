"""In-process coverage for the stdio transport loop (no subprocess).

Drives :meth:`MCPServer.serve` and :func:`serve_stdio` with ``io.StringIO``
streams so the newline-delimited framing, empty-line skipping, EOF handling,
the internal-error recovery branch, and the ``serve_stdio`` stdin/stdout wiring
are exercised directly by the fast suite (the subprocess test in
``test_mcp_stdio.py`` covers the real-process path separately).
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

from executionkit._mock import MockProvider
from executionkit.mcp import server as server_module
from executionkit.mcp._constants import INTERNAL_ERROR, PARSE_ERROR
from executionkit.mcp.server import MCPServer, serve_stdio

if TYPE_CHECKING:
    import pytest


def _lines(raw: str) -> list[dict]:
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


class TestServeLoop:
    async def test_serve_processes_requests_and_skips_notifications(self) -> None:
        provider = MockProvider(responses=["Paris"])
        server = MCPServer(provider_factory=lambda: provider)
        # A blank line (skipped), an initialize request, a notification (no
        # response), and a tools/list request — then EOF.
        reader = io.StringIO(
            "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
            + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            + "\n"
        )
        writer = io.StringIO()

        await server.serve(reader, writer)

        responses = _lines(writer.getvalue())
        # Two responses: ping (id 1) and tools/list (id 2). Notification: none.
        ids = [response["id"] for response in responses]
        assert ids == [1, 2]
        assert responses[0]["result"] == {}
        assert {t["name"] for t in responses[1]["result"]["tools"]} == {
            "consensus",
            "react_loop",
        }

    async def test_serve_emits_parse_error_for_bad_line_and_continues(self) -> None:
        server = MCPServer(provider_factory=lambda: None)
        reader = io.StringIO(
            "{ this is not json\n"
            + json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping"})
            + "\n"
        )
        writer = io.StringIO()

        await server.serve(reader, writer)

        responses = _lines(writer.getvalue())
        # The bad line yields a parse error (loop does NOT terminate); the valid
        # ping still gets answered afterwards.
        assert responses[0]["error"]["code"] == PARSE_ERROR
        assert responses[1]["id"] == 5

    async def test_serve_stops_at_eof(self) -> None:
        server = MCPServer(provider_factory=lambda: None)
        writer = io.StringIO()
        # Empty input == immediate EOF; serve returns without writing anything.
        await server.serve(io.StringIO(""), writer)
        assert writer.getvalue() == ""


class TestProcessLineInternalError:
    async def test_dispatch_failure_becomes_internal_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server = MCPServer(provider_factory=lambda: None)

        async def _boom(_message: object) -> dict:
            raise RuntimeError("dispatch exploded")

        # Force handle_message to raise so the transport's recovery branch runs.
        monkeypatch.setattr(server, "handle_message", _boom)
        response = await server._process_line(
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        )
        assert response is not None
        assert response["error"]["code"] == INTERNAL_ERROR
        # The id is recovered from the raw message even though dispatch failed.
        assert response["id"] == 3


class TestMainEntryPoint:
    def test_main_runs_serve_stdio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from executionkit.mcp import __main__ as main_module

        called: list[bool] = []

        async def _fake_serve_stdio() -> None:
            called.append(True)

        monkeypatch.setattr(main_module, "serve_stdio", _fake_serve_stdio)
        main_module.main()
        assert called == [True]

    def test_main_suppresses_keyboard_interrupt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from executionkit.mcp import __main__ as main_module

        async def _interrupt() -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(main_module, "serve_stdio", _interrupt)
        # main() must swallow KeyboardInterrupt (normal stdio-server shutdown).
        main_module.main()


class TestServeStdio:
    async def test_serve_stdio_uses_stdin_stdout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = MockProvider(responses=["ok"])
        fake_stdin = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
        )
        fake_stdout = io.StringIO()
        # io.StringIO has no reconfigure(), so serve_stdio's getattr guard skips
        # the UTF-8 reconfigure step cleanly on these fakes.
        monkeypatch.setattr(server_module.sys, "stdin", fake_stdin)
        monkeypatch.setattr(server_module.sys, "stdout", fake_stdout)

        await serve_stdio(provider_factory=lambda: provider)

        responses = _lines(fake_stdout.getvalue())
        assert responses[0]["id"] == 1
        assert {t["name"] for t in responses[0]["result"]["tools"]} == {
            "consensus",
            "react_loop",
        }
