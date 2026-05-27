"""Message construction helpers for OpenAI-compatible chat format."""

from __future__ import annotations

from typing import Any


def user_message(content: str) -> dict[str, Any]:
    """Return an OpenAI-compatible user role message dict."""
    return {"role": "user", "content": content}


def assistant_message(content: str) -> dict[str, Any]:
    """Return an OpenAI-compatible assistant role message dict."""
    return {"role": "assistant", "content": content}
