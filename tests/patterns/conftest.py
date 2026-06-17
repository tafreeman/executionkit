"""Shared fixtures and helpers for tests/patterns/ sub-suite.

Imports that every pattern test file needs are centralised here so each file
only has to import from conftest rather than repeat the same block.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.provider import LLMResponse, ToolCall
from executionkit.types import Tool

# ---------------------------------------------------------------------------
# Response builders — used by react_loop tests and shared cross-pattern tests
# ---------------------------------------------------------------------------


def make_tool_response(
    tool_name: str, tool_id: str, args: dict[str, Any]
) -> LLMResponse:
    """Create an LLMResponse that requests a tool call."""
    return LLMResponse(
        content="",
        finish_reason="tool_calls",
        tool_calls=(ToolCall(id=tool_id, name=tool_name, arguments=args),),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
    )


def make_final_response(content: str) -> LLMResponse:
    """Create an LLMResponse with a final text answer (no tool calls)."""
    return LLMResponse(
        content=content,
        finish_reason="stop",
        tool_calls=(),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 20}),
    )


# ---------------------------------------------------------------------------
# pytest fixtures — available to all tests/patterns/ modules automatically
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider() -> MockProvider:
    """Basic mock provider returning a single simple response."""
    return MockProvider(responses=["Hello, world!"])


@pytest.fixture
def multi_response_provider() -> MockProvider:
    """Mock provider with multiple distinct responses for consensus testing."""
    return MockProvider(
        responses=["answer_a", "answer_a", "answer_a", "answer_b", "answer_a"]
    )


@pytest.fixture
def empty_provider() -> MockProvider:
    """Mock provider with no pre-configured responses (returns empty string)."""
    return MockProvider(responses=[])


@pytest.fixture
def make_llm_response():
    """Factory fixture to create LLMResponse objects with sensible defaults."""

    def _make(
        content: str = "",
        finish_reason: str = "stop",
        tool_calls: list[ToolCall] | None = None,
        input_tokens: int = 10,
        output_tokens: int = 5,
    ) -> LLMResponse:
        return LLMResponse(
            content=content,
            finish_reason=finish_reason,
            tool_calls=tuple(tool_calls or []),
            usage=MappingProxyType(
                {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                }
            ),
        )

    return _make


@pytest.fixture
def search_tool() -> Tool:
    """A simple search tool returning a fixed string."""

    async def _execute(query: str) -> str:
        return "search result"

    return Tool(
        name="search",
        description="Search the web",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        execute=_execute,
    )
