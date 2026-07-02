"""Named constants for the MCP server — no magic numbers in the protocol code.

Groups the JSON-RPC framing tokens, error codes, protocol-version strings, and
tool-argument bounds used by :mod:`executionkit.mcp.server` and
:mod:`executionkit.mcp.tools` so they stay in one auditable place.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 framing
# ---------------------------------------------------------------------------

JSONRPC_VERSION: Final[str] = "2.0"
"""The only ``jsonrpc`` version string this server emits or accepts."""

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 standard error codes
# https://www.jsonrpc.org/specification#error_object
# ---------------------------------------------------------------------------

PARSE_ERROR: Final[int] = -32700
"""Invalid JSON was received (message could not be parsed)."""

INVALID_REQUEST: Final[int] = -32600
"""The JSON sent is not a valid Request object."""

METHOD_NOT_FOUND: Final[int] = -32601
"""The requested method does not exist or is not available."""

INVALID_PARAMS: Final[int] = -32602
"""Invalid method parameter(s)."""

INTERNAL_ERROR: Final[int] = -32603
"""Internal JSON-RPC error."""

# ---------------------------------------------------------------------------
# MCP protocol
# ---------------------------------------------------------------------------

SERVER_NAME: Final[str] = "executionkit"
"""Server name reported in the ``initialize`` result ``serverInfo``."""

PROTOCOL_VERSION: Final[str] = "2025-06-18"
"""MCP protocol version this server implements and prefers.

When a client requests a protocol version we recognise (see
:data:`SUPPORTED_PROTOCOL_VERSIONS`), the server echoes the client's version;
otherwise it responds with this one, per the MCP version-negotiation rule.
"""

SUPPORTED_PROTOCOL_VERSIONS: Final[frozenset[str]] = frozenset(
    {
        "2024-11-05",
        "2025-03-26",
        PROTOCOL_VERSION,
    }
)
"""Protocol versions the server will accept if a client proposes one of them."""

# ---------------------------------------------------------------------------
# Tool-argument bounds (defence-in-depth against runaway MCP callers)
# ---------------------------------------------------------------------------

MIN_CONSENSUS_SAMPLES: Final[int] = 1
"""Lower bound for the ``consensus`` tool's ``n`` argument."""

MAX_CONSENSUS_SAMPLES: Final[int] = 9
"""Upper bound for the ``consensus`` tool's ``n`` argument.

Bounded so a single MCP call cannot fan out an unbounded number of LLM
completions. Callers needing more should use the library API directly.
"""

DEFAULT_CONSENSUS_SAMPLES: Final[int] = 3
"""Default sample count when the ``consensus`` caller omits ``n``."""

MIN_TEMPERATURE: Final[float] = 0.0
"""Lower bound for a tool's ``temperature`` argument."""

MAX_TEMPERATURE: Final[float] = 2.0
"""Upper bound for a tool's ``temperature`` argument."""

MIN_REACT_ROUNDS: Final[int] = 1
"""Lower bound for the ``react_loop`` tool's ``max_rounds`` argument."""

MAX_REACT_ROUNDS: Final[int] = 8
"""Upper bound for the ``react_loop`` tool's ``max_rounds`` argument."""

DEFAULT_REACT_ROUNDS: Final[int] = 5
"""Default round cap when the ``react_loop`` caller omits ``max_rounds``."""
