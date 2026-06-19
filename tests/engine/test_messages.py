"""Tests for executionkit.engine.messages construction helpers."""

from __future__ import annotations

import json

from executionkit.engine.messages import (
    assistant_message,
    assistant_tool_calls_message,
    system_message,
    tool_message,
    user_message,
)
from executionkit.provider import ToolCall


def test_system_message() -> None:
    assert system_message("be terse") == {"role": "system", "content": "be terse"}


def test_user_message() -> None:
    assert user_message("hi") == {"role": "user", "content": "hi"}


def test_assistant_message() -> None:
    assert assistant_message("ok") == {"role": "assistant", "content": "ok"}


def test_tool_message() -> None:
    assert tool_message("tc1", "42") == {
        "role": "tool",
        "tool_call_id": "tc1",
        "content": "42",
    }


def test_assistant_tool_calls_message_serializes_arguments() -> None:
    tc = ToolCall(id="tc1", name="search", arguments={"query": "hi"})
    msg = assistant_tool_calls_message("thinking", [tc])

    assert msg["role"] == "assistant"
    assert msg["content"] == "thinking"
    (call,) = msg["tool_calls"]
    assert call["id"] == "tc1"
    assert call["type"] == "function"
    assert call["function"]["name"] == "search"
    # Arguments are JSON-encoded per the OpenAI schema.
    assert json.loads(call["function"]["arguments"]) == {"query": "hi"}


def test_assistant_tool_calls_message_empty_content_is_none() -> None:
    """An assistant turn that only requests tools carries content=None."""
    tc = ToolCall(id="tc1", name="noop", arguments={})
    msg = assistant_tool_calls_message("", [tc])
    assert msg["content"] is None


def test_assistant_tool_calls_message_no_calls() -> None:
    assert assistant_tool_calls_message("hi", []) == {
        "role": "assistant",
        "content": "hi",
        "tool_calls": [],
    }
