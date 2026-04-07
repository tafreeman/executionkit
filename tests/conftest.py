"""Shared pytest fixtures for ExecutionKit tests."""

from __future__ import annotations

import pytest

from executionkit._mock import MockProvider
from executionkit.provider import LLMResponse, ToolCall


@pytest.fixture
def mock_provider() -> MockProvider:
    """Basic mock provider returning simple responses."""
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
            tool_calls=tool_calls or [],
            usage={
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
            },
        )

    return _make
