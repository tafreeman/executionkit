"""JSON-RPC 2.0 dispatch and stdio transport for the ExecutionKit MCP server.

The protocol surface is deliberately small and correct:

* **Transport** — stdio only: newline-delimited JSON-RPC 2.0 messages read from
  stdin and written to stdout, UTF-8. One JSON object per line.
* **Handshake** — ``initialize`` (negotiate ``protocolVersion``; advertise only
  the ``tools`` capability) followed by the ``notifications/initialized``
  notification.
* **Tools** — ``tools/list`` returns JSON-Schema tool definitions; ``tools/call``
  executes a tool and returns an MCP ``content`` result. Tool-level failures are
  returned as ``isError: True`` results (not JSON-RPC errors); malformed frames
  and unknown methods return the standard JSON-RPC error codes.
* **ping** — answered with an empty result.

Notifications (requests without an ``id``) never receive a response; unknown
notifications are ignored silently per JSON-RPC.

The dispatch layer (:meth:`MCPServer.handle_message`) is pure and in-process
testable: feed it a decoded request dict and it returns the response dict (or
``None`` for notifications) — no subprocess or real I/O required. A
``provider_factory`` is injectable so tests can supply a ``MockProvider``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any

import executionkit
from executionkit.mcp._constants import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    JSONRPC_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    SERVER_NAME,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from executionkit.mcp.tools import (
    ProviderFactory,
    ToolExecutionError,
    _memoize_provider,
    get_handler,
    list_tools,
    provider_from_env,
)

if TYPE_CHECKING:
    from typing import TextIO

# Sentinel distinguishing "no id present" (a notification) from a real id whose
# value happens to be ``None``. JSON-RPC forbids that, but we treat a literal
# null id as a request needing a response, and an absent id as a notification.
_NO_ID: Any = object()


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 error response object."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _result_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC 2.0 success response object."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def _negotiate_protocol_version(requested: Any) -> str:
    """Return the protocol version to report back to the client.

    Echo the client's requested version when we support it; otherwise respond
    with our own preferred version, per MCP version negotiation.
    """
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return PROTOCOL_VERSION


class MCPServer:
    """MCP protocol dispatcher for ExecutionKit tools.

    Holds the (injectable) provider factory and the post-``initialize`` state.
    :meth:`handle_message` maps one decoded JSON-RPC message to its response
    (or ``None`` for notifications); :meth:`serve` drives the stdio loop.
    """

    def __init__(self, provider_factory: ProviderFactory | None = None) -> None:
        """Create a server.

        Args:
            provider_factory: Zero-arg callable returning an
                :class:`~executionkit.provider.LLMProvider` or ``None`` when
                unconfigured. Defaults to
                :func:`~executionkit.mcp.tools.provider_from_env`. Inject a
                factory returning a ``MockProvider`` in tests.
        """
        # Memoize only the default env factory: each Provider it builds may own
        # an httpx.AsyncClient (with the executionkit[httpx] extra installed),
        # so constructing one per tools/call would leak clients. An injected
        # factory stays caller-managed and is invoked as-is.
        self._provider_factory: ProviderFactory = (
            provider_factory
            if provider_factory is not None
            else _memoize_provider(provider_from_env)
        )
        self._initialized: bool = False

    # -- request handlers ---------------------------------------------------

    def _handle_initialize(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle the ``initialize`` handshake request."""
        self._initialized = True
        protocol_version = _negotiate_protocol_version(params.get("protocolVersion"))
        result = {
            "protocolVersion": protocol_version,
            # Advertise ONLY the tools capability — resources/prompts/sampling
            # are intentionally not implemented.
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": SERVER_NAME,
                "version": executionkit.__version__,
            },
        }
        return _result_response(request_id, result)

    def _handle_tools_list(self, request_id: Any) -> dict[str, Any]:
        """Handle ``tools/list`` — return the JSON-Schema tool definitions."""
        return _result_response(request_id, {"tools": list_tools()})

    async def _handle_tools_call(
        self, request_id: Any, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle ``tools/call`` — dispatch to a tool handler.

        A successful call returns an MCP result with ``content`` and
        ``isError: False``. A tool-level failure (unknown tool, bad arguments,
        missing provider, or an unexpected exception in the handler) returns
        ``isError: True`` with a message — never a JSON-RPC error — so the model
        receives an error result it can act on. Only a structurally invalid
        ``params`` object yields a JSON-RPC ``INVALID_PARAMS`` error.
        """
        name = params.get("name")
        if not isinstance(name, str):
            return _error_response(
                request_id, INVALID_PARAMS, "tools/call requires a string 'name'"
            )
        raw_arguments = params.get("arguments", {})
        if not isinstance(raw_arguments, dict):
            return _error_response(
                request_id, INVALID_PARAMS, "tools/call 'arguments' must be an object"
            )

        handler = get_handler(name)
        if handler is None:
            return _result_response(
                request_id, _tool_error_content(f"Unknown tool: '{name}'")
            )

        try:
            text = await handler(raw_arguments, self._provider_factory)
        except ToolExecutionError as exc:
            return _result_response(request_id, _tool_error_content(str(exc)))
        except Exception as exc:
            # Defensive: any unexpected handler error becomes an isError result
            # (type name only — the message may carry provider/argument detail)
            # rather than crashing the server or leaking internals to the client.
            return _result_response(
                request_id,
                _tool_error_content(f"Tool '{name}' failed: {type(exc).__name__}"),
            )
        return _result_response(request_id, _tool_success_content(text))

    # -- dispatch -----------------------------------------------------------

    async def handle_message(self, message: Any) -> dict[str, Any] | None:
        """Dispatch one decoded JSON-RPC message and return the response.

        Returns ``None`` when *message* is a notification (no ``id``), so the
        transport writes nothing back. Returns a response dict for requests,
        including JSON-RPC error responses for malformed requests and unknown
        methods.
        """
        if not isinstance(message, dict):
            return _error_response(
                None, INVALID_REQUEST, "JSON-RPC message must be an object"
            )

        request_id = message.get("id", _NO_ID)
        is_notification = request_id is _NO_ID

        if message.get("jsonrpc") != JSONRPC_VERSION:
            if is_notification:
                return None
            return _error_response(
                request_id,
                INVALID_REQUEST,
                f"Request 'jsonrpc' must be '{JSONRPC_VERSION}'",
            )

        method = message.get("method")

        if not isinstance(method, str):
            if is_notification:
                return None
            return _error_response(
                request_id, INVALID_REQUEST, "Request 'method' must be a string"
            )

        params = message.get("params", {})
        if not isinstance(params, dict):
            params = {}

        # Notifications: never respond. Unknown notifications are ignored.
        if is_notification:
            return None

        # MCP handshake gating: before a successful `initialize`, only
        # `initialize` itself and `ping` are served.
        if not self._initialized and method not in ("initialize", "ping"):
            return _error_response(
                request_id,
                INVALID_REQUEST,
                "Server not initialized: send 'initialize' before other requests",
            )

        if method == "initialize":
            return self._handle_initialize(request_id, params)
        if method == "ping":
            return _result_response(request_id, {})
        if method == "tools/list":
            return self._handle_tools_list(request_id)
        if method == "tools/call":
            return await self._handle_tools_call(request_id, params)

        return _error_response(
            request_id, METHOD_NOT_FOUND, f"Method not found: '{method}'"
        )

    # -- stdio transport ----------------------------------------------------

    async def serve(self, reader: TextIO, writer: TextIO) -> None:
        """Run the newline-delimited JSON-RPC loop over *reader*/*writer*.

        Reads one JSON object per line from *reader* until EOF. Each line is
        parsed, decoded, and dispatched; any response is written to *writer* as
        a single line and flushed. A line that is not valid JSON yields a
        JSON-RPC parse error (id ``null``) rather than terminating the loop.

        *reader* and *writer* are blocking text streams (e.g. ``sys.stdin`` /
        ``sys.stdout``); the blocking ``readline``/``write`` calls are moved off
        the event loop with :func:`asyncio.to_thread`, so concurrent tool work
        inside :meth:`handle_message` (e.g. ``consensus`` fan-out) still runs.
        This thread-based approach is portable to Windows, where wrapping the
        standard stdio handles in asyncio pipe transports is not supported.
        """
        while True:
            line = await asyncio.to_thread(reader.readline)
            if not line:
                break
            stripped = line.strip()
            if not stripped:
                continue
            response = await self._process_line(stripped)
            if response is not None:
                await asyncio.to_thread(self._write_message, writer, response)

    async def _process_line(self, raw: str) -> dict[str, Any] | None:
        """Decode one raw line into a response dict (or ``None`` for notifications)."""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return _error_response(None, PARSE_ERROR, "Parse error: invalid JSON")
        try:
            return await self.handle_message(message)
        except Exception:
            # A bug in dispatch must not kill the transport loop; report an
            # internal error keyed to the request id when we can recover it.
            request_id = message.get("id") if isinstance(message, dict) else None
            return _error_response(request_id, INTERNAL_ERROR, "Internal server error")

    @staticmethod
    def _write_message(writer: TextIO, message: dict[str, Any]) -> None:
        """Serialise *message* to a single JSON line and flush it.

        Runs on a worker thread (via :func:`asyncio.to_thread`); the flush
        guarantees the client sees the response before the next blocking read.
        """
        writer.write(json.dumps(message) + "\n")
        writer.flush()


async def handle_message(
    message: Any, provider_factory: ProviderFactory | None = None
) -> dict[str, Any] | None:
    """Convenience one-shot dispatch of a single JSON-RPC *message*.

    Constructs a fresh :class:`MCPServer` and dispatches *message*. Handy for
    unit tests that only need to exercise a single request/response pair; for a
    multi-message conversation reuse one :class:`MCPServer` instance so
    ``initialize`` state carries across calls. The one-shot server is treated
    as already initialized — handshake gating only makes sense across a
    conversation.
    """
    server = MCPServer(provider_factory=provider_factory)
    server._initialized = True
    return await server.handle_message(message)


async def serve_stdio(provider_factory: ProviderFactory | None = None) -> None:
    """Serve the MCP protocol over this process's stdin/stdout until EOF.

    Reconfigures ``sys.stdin`` / ``sys.stdout`` to UTF-8 (the MCP stdio wire
    encoding) when the running interpreter supports it, then drives the
    newline-delimited JSON-RPC loop until stdin closes.

    Args:
        provider_factory: Optional provider factory override (see
            :class:`MCPServer`). Defaults to env-based resolution.
    """
    # MCP stdio framing is UTF-8; force it so a non-UTF-8 locale cannot corrupt
    # multibyte payloads. reconfigure() exists on TextIOWrapper (CPython stdio).
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="")

    server = MCPServer(provider_factory=provider_factory)
    await server.serve(sys.stdin, sys.stdout)


def _tool_success_content(text: str) -> dict[str, Any]:
    """Build a successful MCP ``tools/call`` result payload."""
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _tool_error_content(message: str) -> dict[str, Any]:
    """Build an MCP ``tools/call`` *error* result payload (``isError: True``)."""
    return {"content": [{"type": "text", "text": message}], "isError": True}
