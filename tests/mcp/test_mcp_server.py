"""Unit tests for the ExecutionKit MCP server dispatch layer.

The dispatch layer is exercised entirely in-process: JSON-RPC message dicts are
fed to :meth:`MCPServer.handle_message` (or :meth:`MCPServer._process_line` for
raw-bytes parse-error coverage) and the response dicts are asserted. A
``MockProvider`` is injected via the provider factory, so no subprocess, network,
or real LLM is involved. The one subprocess round-trip lives in
``test_mcp_stdio.py``.
"""

from __future__ import annotations

import json

import pytest

from executionkit._mock import MockProvider
from executionkit.mcp._constants import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
)
from executionkit.mcp.server import MCPServer, handle_message
from executionkit.mcp.tools import _memoize_provider, provider_from_env
from executionkit.provider import LLMProvider, LLMResponse

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_server(provider: LLMProvider | None) -> MCPServer:
    """Build an already-initialized server whose factory returns *provider*.

    Marked initialized so tool-dispatch tests skip the handshake; the handshake
    and its gating are covered by ``TestHandshake`` and
    ``TestPreInitializeGating``.
    """
    server = MCPServer(provider_factory=lambda: provider)
    server._initialized = True
    return server


def _initialize_request(protocol_version: str = PROTOCOL_VERSION) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": protocol_version, "capabilities": {}},
    }


def _tools_call_request(name: str, arguments: dict, request_id: int = 2) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


@pytest.fixture
def consensus_server() -> MCPServer:
    """Server backed by a MockProvider that always answers 'Paris'."""
    provider = MockProvider(responses=["Paris", "Paris", "Paris"])
    return _make_server(provider)


# ---------------------------------------------------------------------------
# Handshake
# ---------------------------------------------------------------------------


class TestHandshake:
    async def test_initialize_advertises_only_tools_capability(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(_initialize_request())
        result = response["result"]
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert result["capabilities"] == {"tools": {}}
        assert "resources" not in result["capabilities"]
        assert "prompts" not in result["capabilities"]
        assert result["serverInfo"]["name"] == "executionkit"
        assert result["serverInfo"]["version"]

    async def test_initialize_echoes_supported_client_version(
        self, consensus_server: MCPServer
    ) -> None:
        # A version the server supports is echoed back verbatim.
        response = await consensus_server.handle_message(
            _initialize_request("2024-11-05")
        )
        assert response["result"]["protocolVersion"] == "2024-11-05"

    async def test_initialize_falls_back_to_server_version(
        self, consensus_server: MCPServer
    ) -> None:
        # An unrecognised client version yields the server's own preferred one.
        response = await consensus_server.handle_message(
            _initialize_request("1999-01-01")
        )
        assert response["result"]["protocolVersion"] == PROTOCOL_VERSION

    async def test_initialized_notification_gets_no_response(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        assert response is None

    async def test_unknown_notification_ignored_silently(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "method": "notifications/somethingElse"}
        )
        assert response is None

    async def test_ping_returns_empty_result(self, consensus_server: MCPServer) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "id": 7, "method": "ping"}
        )
        assert response["result"] == {}
        assert response["id"] == 7


# ---------------------------------------------------------------------------
# tools/list
# ---------------------------------------------------------------------------


class TestToolsList:
    async def test_lists_both_tools(self, consensus_server: MCPServer) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        names = {tool["name"] for tool in response["result"]["tools"]}
        assert names == {"consensus", "react_loop"}

    async def test_every_tool_has_object_input_schema(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        for tool in response["result"]["tools"]:
            schema = tool["inputSchema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "description" in tool
            # Every tool requires a prompt.
            assert "prompt" in schema["required"]

    async def test_consensus_schema_bounds_sample_count(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        consensus = next(
            tool for tool in response["result"]["tools"] if tool["name"] == "consensus"
        )
        n_schema = consensus["inputSchema"]["properties"]["n"]
        assert n_schema["type"] == "integer"
        assert n_schema["minimum"] >= 1
        assert n_schema["maximum"] >= n_schema["minimum"]
        # strategy is an enum of the real VotingStrategy values.
        strategy_schema = consensus["inputSchema"]["properties"]["strategy"]
        assert set(strategy_schema["enum"]) == {"majority", "unanimous"}

    async def test_tools_list_is_json_serialisable(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        # Must round-trip through JSON for the stdio transport.
        assert json.loads(json.dumps(response)) == response


# ---------------------------------------------------------------------------
# tools/call — success
# ---------------------------------------------------------------------------


class TestConsensusCall:
    async def test_successful_consensus_returns_text_content(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("consensus", {"prompt": "capital of France?", "n": 3})
        )
        result = response["result"]
        assert result["isError"] is False
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"].splitlines()[0] == "Paris"

    async def test_consensus_reports_agreement_and_cost(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("consensus", {"prompt": "x", "n": 3})
        )
        text = response["result"]["content"][0]["text"]
        assert "agreement_ratio:" in text
        assert "unique_responses:" in text
        assert "llm_calls=" in text

    async def test_consensus_defaults_sample_count_when_omitted(self) -> None:
        provider = MockProvider(responses=["yes"])
        server = _make_server(provider)
        response = await server.handle_message(
            _tools_call_request("consensus", {"prompt": "decide"})
        )
        assert response["result"]["isError"] is False
        # DEFAULT_CONSENSUS_SAMPLES calls dispatched to the provider.
        assert provider.call_count >= 1

    async def test_consensus_forwards_temperature(self) -> None:
        provider = MockProvider(responses=["yes"])
        server = _make_server(provider)
        response = await server.handle_message(
            _tools_call_request(
                "consensus", {"prompt": "decide", "n": 1, "temperature": 0.2}
            )
        )
        assert response["result"]["isError"] is False
        # The temperature argument reached the provider call.
        assert provider.last_call is not None
        assert provider.last_call.temperature == 0.2

    async def test_consensus_rejects_non_integer_sample_count(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("consensus", {"prompt": "x", "n": "three"})
        )
        assert response["result"]["isError"] is True
        assert "integer" in response["result"]["content"][0]["text"]

    async def test_consensus_rejects_out_of_range_temperature(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("consensus", {"prompt": "x", "n": 1, "temperature": 9})
        )
        assert response["result"]["isError"] is True
        assert "temperature" in response["result"]["content"][0]["text"]

    async def test_consensus_rejects_non_numeric_temperature(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request(
                "consensus", {"prompt": "x", "n": 1, "temperature": "hot"}
            )
        )
        assert response["result"]["isError"] is True
        assert "number" in response["result"]["content"][0]["text"]


class _NonToolProvider:
    """An LLMProvider that does NOT support tool calling (supports_tools absent)."""

    async def complete(
        self,
        messages: object,
        **kwargs: object,
    ) -> LLMResponse:
        return LLMResponse(content="no tools here")


class TestReactLoopCall:
    async def test_react_loop_runs_with_demo_tools(self) -> None:
        # A final (no-tool-call) response ends the loop on round 1.
        provider = MockProvider(responses=[LLMResponse(content="done")])
        server = _make_server(provider)
        response = await server.handle_message(
            _tools_call_request("react_loop", {"prompt": "say done"})
        )
        result = response["result"]
        assert result["isError"] is False
        text = result["content"][0]["text"]
        assert text.splitlines()[0] == "done"
        assert "rounds:" in text
        assert "tool_calls_made:" in text

    async def test_react_loop_rejects_non_tool_calling_provider(self) -> None:
        server = MCPServer(provider_factory=_NonToolProvider)
        server._initialized = True
        response = await server.handle_message(
            _tools_call_request("react_loop", {"prompt": "hi"})
        )
        result = response["result"]
        assert result["isError"] is True
        assert "tool calling" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# tools/call — error paths (isError results, NOT JSON-RPC errors)
# ---------------------------------------------------------------------------


class TestToolErrorResults:
    async def test_missing_provider_env_returns_is_error(self) -> None:
        server = _make_server(None)  # factory yields no provider
        response = await server.handle_message(
            _tools_call_request("consensus", {"prompt": "x"})
        )
        result = response["result"]
        # Fail informative, not crash: a well-formed isError result, not a
        # JSON-RPC error object.
        assert "error" not in response
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "EXECUTIONKIT_BASE_URL" in text
        assert "EXECUTIONKIT_MODEL" in text

    async def test_unknown_tool_returns_is_error(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("does_not_exist", {"prompt": "x"})
        )
        assert "error" not in response
        assert response["result"]["isError"] is True
        assert "Unknown tool" in response["result"]["content"][0]["text"]

    async def test_missing_prompt_returns_is_error(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("consensus", {"n": 3})
        )
        assert response["result"]["isError"] is True
        assert "prompt" in response["result"]["content"][0]["text"]

    async def test_out_of_range_sample_count_returns_is_error(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("consensus", {"prompt": "x", "n": 9999})
        )
        assert response["result"]["isError"] is True
        assert "'n'" in response["result"]["content"][0]["text"]

    async def test_bad_strategy_returns_is_error(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            _tools_call_request("consensus", {"prompt": "x", "strategy": "plurality"})
        )
        assert response["result"]["isError"] is True
        assert "strategy" in response["result"]["content"][0]["text"]

    async def test_provider_exception_becomes_is_error(self) -> None:
        # A provider that raises must not crash the server: the handler's
        # unexpected-exception guard converts it to an isError result.
        provider = MockProvider(exception=RuntimeError("boom"))
        server = _make_server(provider)
        response = await server.handle_message(
            _tools_call_request("consensus", {"prompt": "x", "n": 1})
        )
        assert "error" not in response
        assert response["result"]["isError"] is True


# ---------------------------------------------------------------------------
# JSON-RPC protocol errors
# ---------------------------------------------------------------------------


class TestJsonRpcErrors:
    async def test_parse_error_on_invalid_json(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server._process_line("{not valid json")
        assert response is not None
        assert response["error"]["code"] == PARSE_ERROR
        assert response["id"] is None

    async def test_method_not_found(self, consensus_server: MCPServer) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list"}
        )
        assert response["error"]["code"] == METHOD_NOT_FOUND
        assert response["id"] == 5

    async def test_invalid_params_when_name_not_string(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": 42}}
        )
        assert response["error"]["code"] == INVALID_PARAMS

    async def test_invalid_params_when_arguments_not_object(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "consensus", "arguments": "oops"},
            }
        )
        assert response["error"]["code"] == INVALID_PARAMS

    async def test_non_object_message_is_invalid_request(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message([1, 2, 3])
        assert response is not None
        assert "error" in response

    async def test_request_without_method_is_invalid(
        self, consensus_server: MCPServer
    ) -> None:
        response = await consensus_server.handle_message({"jsonrpc": "2.0", "id": 9})
        assert response["error"]["code"] is not None
        assert response["id"] == 9


# ---------------------------------------------------------------------------
# provider_from_env
# ---------------------------------------------------------------------------


class TestProviderFromEnv:
    def test_returns_none_without_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EXECUTIONKIT_BASE_URL", raising=False)
        monkeypatch.setenv("EXECUTIONKIT_MODEL", "test-model")
        assert provider_from_env() is None

    def test_returns_none_without_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTIONKIT_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.delenv("EXECUTIONKIT_MODEL", raising=False)
        assert provider_from_env() is None

    def test_builds_provider_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EXECUTIONKIT_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("EXECUTIONKIT_MODEL", "test-model")
        monkeypatch.setenv("EXECUTIONKIT_API_KEY", "secret")
        provider = provider_from_env()
        assert provider is not None
        assert provider.model == "test-model"


# ---------------------------------------------------------------------------
# One-shot convenience dispatcher
# ---------------------------------------------------------------------------


async def test_handle_message_convenience_one_shot() -> None:
    provider = MockProvider(responses=["ok"])

    def factory() -> LLMProvider:
        return provider

    response = await handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        provider_factory=factory,
    )
    assert response is not None
    assert {t["name"] for t in response["result"]["tools"]} == {
        "consensus",
        "react_loop",
    }


# ---------------------------------------------------------------------------
# Handshake gating, JSON-RPC version validation, default-factory memoization
# ---------------------------------------------------------------------------


class TestPreInitializeGating:
    async def test_tools_request_before_initialize_is_rejected(self) -> None:
        server = MCPServer(provider_factory=lambda: None)
        response = await server.handle_message(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
        )
        assert response is not None
        assert response["error"]["code"] == INVALID_REQUEST
        assert "initialize" in response["error"]["message"]

    async def test_ping_is_allowed_before_initialize(self) -> None:
        server = MCPServer(provider_factory=lambda: None)
        response = await server.handle_message(
            {"jsonrpc": "2.0", "id": 8, "method": "ping"}
        )
        assert response is not None
        assert response["result"] == {}

    async def test_tools_request_allowed_after_initialize(self) -> None:
        server = MCPServer(provider_factory=lambda: None)
        await server.handle_message(_initialize_request())
        response = await server.handle_message(
            {"jsonrpc": "2.0", "id": 9, "method": "tools/list"}
        )
        assert response is not None
        assert "result" in response


class TestJsonRpcVersionValidation:
    async def test_missing_jsonrpc_field_is_invalid_request(self) -> None:
        server = _make_server(None)
        response = await server.handle_message({"id": 4, "method": "ping"})
        assert response is not None
        assert response["error"]["code"] == INVALID_REQUEST

    async def test_wrong_jsonrpc_version_is_invalid_request(self) -> None:
        server = _make_server(None)
        response = await server.handle_message(
            {"jsonrpc": "1.0", "id": 5, "method": "ping"}
        )
        assert response is not None
        assert response["error"]["code"] == INVALID_REQUEST

    async def test_notification_with_wrong_version_is_ignored(self) -> None:
        server = _make_server(None)
        response = await server.handle_message(
            {"jsonrpc": "1.0", "method": "notifications/initialized"}
        )
        assert response is None


class TestDefaultProviderFactoryMemoization:
    def test_first_non_none_provider_is_cached(self) -> None:
        calls: list[int] = []
        first = MockProvider(responses=["a"])
        second = MockProvider(responses=["b"])
        results: list[LLMProvider | None] = [None, first, second]

        def factory() -> LLMProvider | None:
            calls.append(1)
            return results[len(calls) - 1]

        wrapped = _memoize_provider(factory)
        assert wrapped() is None  # unconfigured result is NOT cached
        assert wrapped() is first  # first real provider is cached...
        assert wrapped() is first  # ...and reused; `second` is never built
        assert len(calls) == 2
