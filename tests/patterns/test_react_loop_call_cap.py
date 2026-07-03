"""Per-round tool-call cap (max_tool_calls_per_round) — the fan-out bound.

Everything a round requests runs concurrently, so the cap is the sandbox's
guard against a buggy/adversarial model requesting an unbounded number of
calls in one turn. Surplus calls must never execute, must still receive a
tool-role rejection observation (so every tool_call_id in the transcript is
answered), and must be counted in ``rejected_tool_calls`` metadata.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from executionkit import react_loop
from executionkit._mock import MockProvider
from executionkit.provider import LLMResponse, ToolCall
from executionkit.types import Tool


def _multi_call_response(count: int) -> LLMResponse:
    return LLMResponse(
        content="",
        finish_reason="tool_calls",
        tool_calls=tuple(
            ToolCall(id=f"tc{i}", name="echo", arguments={"text": f"v{i}"})
            for i in range(count)
        ),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
    )


def _final(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        finish_reason="stop",
        tool_calls=(),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
    )


def _echo_tool(executed: list[str]) -> Tool:
    async def _execute(text: str) -> str:
        executed.append(text)
        return f"echo: {text}"

    return Tool(
        name="echo",
        description="Echo the input text.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        execute=_execute,
    )


class TestMaxToolCallsPerRound:
    async def test_surplus_calls_are_rejected_not_executed(self) -> None:
        executed: list[str] = []
        provider = MockProvider(responses=[_multi_call_response(5), _final("done")])

        result = await react_loop(
            provider,
            "go",
            tools=[_echo_tool(executed)],
            max_tool_calls_per_round=2,
        )

        # Only the first two calls ran; three were rejected.
        assert executed == ["v0", "v1"]
        assert result.metadata["tool_calls_made"] == 2
        assert result.metadata["rejected_tool_calls"] == 3

    async def test_every_tool_call_id_gets_an_answer(self) -> None:
        # The transcript must stay well-formed: an assistant message listing N
        # tool_calls needs N tool-role replies, rejected or not.
        provider = MockProvider(responses=[_multi_call_response(4), _final("done")])
        result = await react_loop(
            provider,
            "go",
            tools=[_echo_tool([])],
            max_tool_calls_per_round=1,
        )
        transcript: tuple[dict[str, Any], ...] = result.metadata["messages"]
        tool_replies = {
            m["tool_call_id"] for m in transcript if m.get("role") == "tool"
        }
        assert tool_replies == {"tc0", "tc1", "tc2", "tc3"}
        rejected = [
            m
            for m in transcript
            if m.get("role") == "tool" and "rejected" in m["content"]
        ]
        assert len(rejected) == 3
        assert "limit of 1" in rejected[0]["content"]

    async def test_rounds_within_cap_are_unaffected(self) -> None:
        executed: list[str] = []
        provider = MockProvider(responses=[_multi_call_response(3), _final("done")])
        result = await react_loop(
            provider,
            "go",
            tools=[_echo_tool(executed)],
            max_tool_calls_per_round=3,
        )
        assert executed == ["v0", "v1", "v2"]
        assert result.metadata["rejected_tool_calls"] == 0

    async def test_cap_below_one_rejected(self) -> None:
        provider = MockProvider(responses=[_final("done")])
        with pytest.raises(ValueError, match="max_tool_calls_per_round"):
            await react_loop(
                provider,
                "go",
                tools=[_echo_tool([])],
                max_tool_calls_per_round=0,
            )
