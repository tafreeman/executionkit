"""End-to-end stdio round-trip test for ``python -m executionkit.mcp``.

Spawns the server as a real subprocess and drives the newline-delimited
JSON-RPC 2.0 stdio transport: ``initialize`` -> ``notifications/initialized``
-> ``tools/list`` -> ``tools/call``. The ``tools/call`` uses the *no-provider*
path (no ``EXECUTIONKIT_*`` env set), so the exchange is fully deterministic and
never touches the network or a real LLM — it asserts the server starts, speaks
well-formed framing, and returns an ``isError`` result for the unconfigured
tool rather than crashing.

This is the single subprocess test; all other MCP coverage is in-process
(``test_mcp_server.py``). It stays in the fast suite: the no-provider path
returns immediately, so the subprocess exits in well under a second once stdin
closes. The repo registers no ``slow`` marker (only ``live``), so none is
applied here.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

# Generous ceiling so a loaded CI box never flakes; the real exchange is fast
# because the no-provider path does no I/O beyond stdin/stdout.
_SUBPROCESS_TIMEOUT_SECONDS = 30


def _encode(messages: list[dict]) -> bytes:
    """Encode JSON-RPC *messages* as newline-delimited UTF-8, one per line."""
    return ("".join(json.dumps(message) + "\n" for message in messages)).encode("utf-8")


def _decode_lines(raw: bytes) -> list[dict]:
    """Decode newline-delimited JSON output into a list of response objects."""
    return [
        json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
    ]


def test_stdio_initialize_list_and_call_round_trip() -> None:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "consensus", "arguments": {"prompt": "ping", "n": 1}},
        },
    ]

    # Inherit the current environment (so the in-tree package resolves) but
    # strip any EXECUTIONKIT_* provider config so the tools/call deterministically
    # takes the no-provider path — no network, no real LLM.
    child_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("EXECUTIONKIT_")
    }
    child_env["PYTHONPATH"] = _repo_root()
    child_env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        [sys.executable, "-m", "executionkit.mcp"],
        input=_encode(requests),
        capture_output=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        env=child_env,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    responses = _decode_lines(completed.stdout)

    # Three responses: the notification produces none.
    by_id = {response.get("id"): response for response in responses}
    assert set(by_id) == {1, 2, 3}

    # initialize handshake.
    init = by_id[1]["result"]
    assert init["capabilities"] == {"tools": {}}
    assert init["protocolVersion"] == "2025-06-18"

    # tools/list schema shape.
    names = {tool["name"] for tool in by_id[2]["result"]["tools"]}
    assert names == {"consensus", "react_loop"}

    # tools/call with no provider configured -> informative isError result.
    call_result = by_id[3]["result"]
    assert call_result["isError"] is True
    assert "EXECUTIONKIT_BASE_URL" in call_result["content"][0]["text"]


def _repo_root() -> str:
    """Return the repo root so the subprocess imports the in-tree package."""
    # tests/mcp/test_mcp_stdio.py -> parents[2] (two directories up) is the repo root.
    return str(pathlib.Path(__file__).resolve().parents[2])
