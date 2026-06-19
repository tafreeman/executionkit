"""Message construction helpers for OpenAI-compatible chat format."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from executionkit.provider import ToolCall


def system_message(content: str) -> dict[str, Any]:
    """Return an OpenAI-compatible system role message dict."""
    return {"role": "system", "content": content}


def user_message(content: str) -> dict[str, Any]:
    """Return an OpenAI-compatible user role message dict."""
    return {"role": "user", "content": content}


def assistant_message(content: str) -> dict[str, Any]:
    """Return an OpenAI-compatible assistant role message dict."""
    return {"role": "assistant", "content": content}


def tool_message(tool_call_id: str, content: str) -> dict[str, Any]:
    """Return an OpenAI-compatible tool role message dict.

    Args:
        tool_call_id: Id of the assistant tool call this result answers.
        content: The tool's (stringified) output.
    """
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def assistant_tool_calls_message(
    content: str | None, tool_calls: Sequence[ToolCall]
) -> dict[str, Any]:
    """Return an assistant message carrying one or more tool calls.

    Mirrors the OpenAI ``tool_calls`` shape providers expect when replaying a
    tool-calling turn back into the conversation.  ``content`` is normalised to
    ``None`` when falsy, since an assistant turn that only requests tools has no
    textual content.

    Args:
        content: Assistant text accompanying the tool calls, if any.
        tool_calls: The :class:`~executionkit.provider.ToolCall` objects to
            serialise (``arguments`` are JSON-encoded per the OpenAI schema).
    """
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(dict(tc.arguments)),
                },
            }
            for tc in tool_calls
        ],
    }
