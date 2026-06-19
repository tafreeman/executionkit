"""Tests for the react_loop() pattern and its helpers.

All tests use MockProvider exclusively — no real API calls are made.
Covers: tool dispatch, concurrency, approval gates, message history trimming,
budget enforcement, arg validation, and the _trim_messages helper.
"""

from __future__ import annotations

import asyncio
import time
from types import MappingProxyType
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.approval import ApprovalGate
from executionkit.patterns.react_loop import (
    _trim_messages,
    react_loop,
)
from executionkit.provider import (
    LLMResponse,
    MaxIterationsError,
    PatternError,
    ToolCall,
)
from executionkit.types import PatternResult, TerminationReason, Tool

# ---------------------------------------------------------------------------
# Local response-builder helpers (mirror the module-level helpers in the
# original file so tests in this module stay self-contained).
# ---------------------------------------------------------------------------


def _make_tool_response(
    tool_name: str, tool_id: str, args: dict[str, Any]
) -> LLMResponse:
    """Helper: create an LLMResponse that requests a tool call."""
    return LLMResponse(
        content="",
        finish_reason="tool_calls",
        tool_calls=(ToolCall(id=tool_id, name=tool_name, arguments=args),),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
    )


def _make_final_response(content: str) -> LLMResponse:
    """Helper: create an LLMResponse with a final text answer (no tool calls)."""
    return LLMResponse(
        content=content,
        finish_reason="stop",
        tool_calls=(),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 20}),
    )


# ---------------------------------------------------------------------------
# react_loop()
# ---------------------------------------------------------------------------


class TestReactLoop:
    def _make_search_tool(self, return_value: str = "search result") -> Tool:
        async def _execute(query: str) -> str:
            return return_value

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

    async def test_simple_tool_call_produces_final_answer(self) -> None:

        tool_response = _make_tool_response("search", "tc1", {"query": "hello"})
        final_response = _make_final_response("The answer is 42")

        provider = MockProvider(responses=[tool_response, final_response])
        tool = self._make_search_tool("search result")

        result = await react_loop(provider, "find hello", tools=[tool])
        assert isinstance(result, PatternResult)
        assert "42" in result.value

    async def test_tool_calls_in_one_round_run_concurrently(self) -> None:

        async def _slow(query: str) -> str:
            await asyncio.sleep(0.2)
            return f"done:{query}"

        slow_tool = Tool(
            name="search",
            description="Slow search",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=_slow,
        )
        multi = LLMResponse(
            content="",
            finish_reason="tool_calls",
            tool_calls=(
                ToolCall(id="tc1", name="search", arguments={"query": "a"}),
                ToolCall(id="tc2", name="search", arguments={"query": "b"}),
                ToolCall(id="tc3", name="search", arguments={"query": "c"}),
            ),
            usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
        )
        provider = MockProvider(responses=[multi, _make_final_response("done")])

        start = time.perf_counter()
        result = await react_loop(provider, "go", tools=[slow_tool], max_rounds=4)
        elapsed = time.perf_counter() - start

        assert result.metadata["tool_calls_made"] == 3
        # Three 0.2s tools run concurrently (~0.2s); sequential would be ~0.6s.
        assert elapsed < 0.45, f"tool calls ran sequentially ({elapsed:.2f}s)"

    async def test_multiple_tool_rounds_before_final_answer(self) -> None:

        call1 = _make_tool_response("search", "tc1", {"query": "first"})
        call2 = _make_tool_response("search", "tc2", {"query": "second"})
        final = _make_final_response("Final synthesis")

        provider = MockProvider(responses=[call1, call2, final])
        tool = self._make_search_tool("data")

        result = await react_loop(provider, "multi-step", tools=[tool], max_rounds=8)
        assert "Final synthesis" in result.value

    async def test_tool_not_found_returns_error_message_in_observation(self) -> None:

        # LLM calls a tool that doesn't exist
        bad_call = _make_tool_response("nonexistent_tool", "tc1", {})
        final = _make_final_response("I couldn't find that tool")

        provider = MockProvider(responses=[bad_call, final])
        tool = self._make_search_tool()

        # Should NOT raise — error becomes an observation and loop continues
        result = await react_loop(provider, "question", tools=[tool])
        assert isinstance(result, PatternResult)

        # The unknown-tool error must be fed back to the LLM as a tool observation
        second_call_messages = provider.calls[1].messages
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected at least one tool observation message"
        observation = tool_msgs[0]["content"]
        assert "Unknown tool 'nonexistent_tool'" in observation

    async def test_denying_approval_gate_blocks_tool_execution(self) -> None:

        # A denied tool call must NOT run; it becomes a bounded observation that
        # is fed back to the LLM. This is the core ApprovalGate safety contract.
        executed: list[str] = []

        async def _execute(query: str) -> str:
            executed.append(query)
            return "should never run"

        guarded_tool = Tool(
            name="search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=_execute,
        )

        tool_call = _make_tool_response("search", "tc1", {"query": "secret"})
        final = _make_final_response("Acknowledged the block")
        provider = MockProvider(responses=[tool_call, final])

        result = await react_loop(
            provider,
            "do something",
            tools=[guarded_tool],
            approval_gate=ApprovalGate.deny_all(reason="not permitted"),
        )
        assert isinstance(result, PatternResult)

        # The tool body must never have executed.
        assert executed == [], "denied tool call must not execute"

        # The denial must surface to the LLM as a bounded tool observation.
        second_call_messages = provider.calls[1].messages
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected a tool observation message"
        observation = tool_msgs[0]["content"]
        assert "blocked by approval" in observation
        assert "not permitted" in observation

    async def test_approving_approval_gate_allows_tool_execution(self) -> None:

        # Contrast with the denial path: an approving gate lets the tool run.
        executed: list[str] = []

        async def _execute(query: str) -> str:
            executed.append(query)
            return "ran ok"

        guarded_tool = Tool(
            name="search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=_execute,
        )

        tool_call = _make_tool_response("search", "tc1", {"query": "ok"})
        final = _make_final_response("done")
        provider = MockProvider(responses=[tool_call, final])

        result = await react_loop(
            provider,
            "do something",
            tools=[guarded_tool],
            approval_gate=ApprovalGate.allow_all(),
        )
        assert isinstance(result, PatternResult)
        assert executed == ["ok"], "approved tool call must execute"

    async def test_max_rounds_exhaustion_raises_max_iterations_error(self) -> None:

        # Always returns a tool call → never reaches a final answer
        always_tool = _make_tool_response("search", "tc1", {"query": "q"})

        provider = MockProvider(responses=[always_tool] * 10)
        tool = self._make_search_tool()

        # Should raise MaxIterationsError after max_rounds
        with pytest.raises(MaxIterationsError):
            await react_loop(provider, "question", tools=[tool], max_rounds=3)

    async def test_tool_timeout_observation_contains_timeout_info(self) -> None:

        async def slow_execute(query: str) -> str:
            await asyncio.sleep(10)
            return "never"

        slow_tool = Tool(
            name="slow",
            description="A slow tool",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=slow_execute,
            timeout=0.01,  # Very short timeout
        )

        tool_call = _make_tool_response("slow", "tc1", {"query": "q"})
        final = _make_final_response("Timed out response")

        provider = MockProvider(responses=[tool_call, final])

        # Should not raise TimeoutError — timeout is handled as observation
        result = await react_loop(
            provider, "question", tools=[slow_tool], tool_timeout=0.01
        )
        assert isinstance(result, PatternResult)

        # The timeout notice must be fed back to the LLM as a tool observation
        second_call_messages = provider.calls[1].messages
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected at least one tool observation message"
        observation = tool_msgs[0]["content"]
        assert "timed out" in observation

    async def test_tool_result_truncated_when_too_long(self) -> None:

        long_result = "x" * 20000  # Exceeds default max_observation_chars=12000

        async def _execute(query: str) -> str:
            return long_result

        big_tool = Tool(
            name="big",
            description="Returns lots of data",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=_execute,
        )

        tool_call = _make_tool_response("big", "tc1", {"query": "q"})
        final = _make_final_response("Done")

        provider = MockProvider(responses=[tool_call, final])

        # Verify the second call to the provider has a truncated observation
        result = await react_loop(
            provider, "question", tools=[big_tool], max_observation_chars=100
        )
        assert isinstance(result, PatternResult)
        assert result.metadata["tool_calls_made"] == 1
        assert result.metadata["truncated_observations"] == 1
        assert result.metadata["rounds"] == 2
        # Inspect the message history that was passed to the second LLM call
        assert provider.call_count == 2
        second_call_messages = provider.calls[1].messages
        # Find the tool result message
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        if tool_msgs:
            content = tool_msgs[0].get("content", "")
            assert len(content) <= 200  # truncated + possible truncation notice

    async def test_result_is_pattern_result_str(self) -> None:

        final = _make_final_response("Answer here")
        provider = MockProvider(responses=[final])
        tool = self._make_search_tool()

        result = await react_loop(provider, "question", tools=[tool])
        assert isinstance(result, PatternResult)
        assert isinstance(result.value, str)

    async def test_no_tool_calls_returns_immediately(self) -> None:

        final = _make_final_response("Direct answer, no tools needed")
        provider = MockProvider(responses=[final])
        tool = self._make_search_tool()

        result = await react_loop(provider, "simple question", tools=[tool])
        assert result.value == "Direct answer, no tools needed"

    async def test_cost_tracks_llm_calls(self) -> None:

        call1 = _make_tool_response("search", "tc1", {"query": "q"})
        final = _make_final_response("Answer")

        provider = MockProvider(responses=[call1, final])
        tool = self._make_search_tool()

        result = await react_loop(provider, "question", tools=[tool])
        assert result.cost.llm_calls == 2

    async def test_finish_reason_stop_on_first_call_terminates_in_one_llm_call(
        self,
    ) -> None:
        """LLM returning finish_reason='stop' immediately exits with 1 LLM call."""

        stop_response = _make_final_response("Immediate answer")
        provider = MockProvider(responses=[stop_response])
        tool = self._make_search_tool()

        result = await react_loop(provider, "direct question", tools=[tool])
        assert result.value == "Immediate answer"
        assert result.cost.llm_calls == 1

    async def test_tool_call_missing_required_arg(self) -> None:
        """Schema requires 'query'; LLM sends empty args -> error observation."""

        bad_call = _make_tool_response("search", "tc1", {})
        final = _make_final_response("Done")

        provider = MockProvider(responses=[bad_call, final])
        tool = self._make_search_tool()

        result = await react_loop(provider, "question", tools=[tool])
        assert isinstance(result, PatternResult)
        second_call_messages = provider.calls[1].messages
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected a tool observation message"
        observation = tool_msgs[0]["content"]
        assert "missing" in observation.lower() or "required" in observation.lower()

    async def test_tool_call_extra_arg_blocked(self) -> None:
        """Schema has additionalProperties: false; extra key -> error observation."""

        async def _execute(query: str) -> str:
            return "result"

        strict_tool = Tool(
            name="strict",
            description="No extras allowed",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            execute=_execute,
        )

        bad_call = _make_tool_response(
            "strict", "tc1", {"query": "hello", "extra": "oops"}
        )
        final = _make_final_response("Done")

        provider = MockProvider(responses=[bad_call, final])

        result = await react_loop(provider, "question", tools=[strict_tool])
        assert isinstance(result, PatternResult)
        second_call_messages = provider.calls[1].messages
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected a tool observation message"
        observation = tool_msgs[0]["content"]
        obs_lower = observation.lower()
        assert "unexpected" in obs_lower or "additional" in obs_lower

    async def test_tool_call_wrong_type(self) -> None:
        """Schema expects integer for 'count'; LLM passes string -> error."""

        async def _execute(count: int) -> str:
            return f"count={count}"

        typed_tool = Tool(
            name="counter",
            description="Needs an integer",
            parameters={
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
            },
            execute=_execute,
        )

        bad_call = _make_tool_response("counter", "tc1", {"count": "five"})
        final = _make_final_response("Done")

        provider = MockProvider(responses=[bad_call, final])

        result = await react_loop(provider, "question", tools=[typed_tool])
        assert isinstance(result, PatternResult)
        second_call_messages = provider.calls[1].messages
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected a tool observation message"
        observation = tool_msgs[0]["content"]
        assert "integer" in observation.lower() or "type" in observation.lower()

    async def test_tool_call_valid_args_pass_through(self) -> None:
        """Valid args bypass validation and reach tool.execute normally."""

        executed: list[str] = []

        async def _execute(query: str) -> str:
            executed.append(query)
            return "found it"

        search_tool = Tool(
            name="search",
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=_execute,
        )

        good_call = _make_tool_response("search", "tc1", {"query": "hello"})
        final = _make_final_response("The answer is here")

        provider = MockProvider(responses=[good_call, final])

        result = await react_loop(provider, "question", tools=[search_tool])
        assert isinstance(result, PatternResult)
        assert executed == ["hello"], "execute must have been called with valid args"

    async def test_tool_call_bool_rejected_as_integer(self) -> None:
        """bool True/False must not pass as integer — bool is int subclass in Python."""

        async def _execute(count: int) -> str:
            return f"count={count}"

        typed_tool = Tool(
            name="counter",
            description="Needs an integer",
            parameters={
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
            },
            execute=_execute,
        )

        bool_call = _make_tool_response("counter", "tc1", {"count": True})
        final = _make_final_response("Done")

        provider = MockProvider(responses=[bool_call, final])

        result = await react_loop(provider, "question", tools=[typed_tool])
        assert isinstance(result, PatternResult)
        second_call_messages = provider.calls[1].messages
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected a tool observation message"
        observation = tool_msgs[0]["content"]
        assert "bool" in observation.lower() or "integer" in observation.lower()


# ---------------------------------------------------------------------------
# react_loop() — MB-009 additional tests
# ---------------------------------------------------------------------------


async def test_react_loop_rejects_plain_llm_provider() -> None:
    """react_loop must raise PatternError when provider lacks supports_tools."""

    class PlainProvider:
        async def complete(self, messages: list, **kwargs: object) -> LLMResponse:
            return LLMResponse(
                content="hi",
                usage=MappingProxyType({"prompt_tokens": 1, "completion_tokens": 1}),
                finish_reason="stop",
                tool_calls=(),
            )

    provider = PlainProvider()
    with pytest.raises((PatternError, TypeError)):
        await react_loop(provider, "hello", tools=[])  # type: ignore[arg-type]


async def test_react_loop_raises_max_iterations_error() -> None:
    """react_loop must raise MaxIterationsError after max_rounds."""

    # Provide LLMResponse objects that always request a (nonexistent) tool call.
    # With tools=[], the tool lookup always returns "Error: Unknown tool",
    # the loop never gets a final answer, and MaxIterationsError is raised.
    looping_response = _make_tool_response("some_tool", "tc1", {"arg": "val"})
    provider = MockProvider(responses=[looping_response] * 20)
    with pytest.raises(MaxIterationsError):
        await react_loop(provider, "loop forever", tools=[], max_rounds=2)


async def test_react_loop_returns_final_answer() -> None:
    """react_loop with no tool calls returns the model's response immediately."""

    provider = MockProvider(responses=[_make_final_response("The answer is 42.")])
    result = await react_loop(provider, "What is 6 * 7?", tools=[])
    assert "42" in result.value
    assert result.cost.llm_calls >= 0


# ---------------------------------------------------------------------------
# react_loop message history trimming — P2-PERF-07
# ---------------------------------------------------------------------------


async def test_react_loop_message_history_trimmed() -> None:
    """max_history_messages limits messages sent to provider each round."""

    executed: list[str] = []

    async def execute_search(**_: object) -> str:
        executed.append("search")
        return "ok"

    tool_response = _make_tool_response("search", "tc1", {"query": "x"})
    final_response = _make_final_response("Done")
    provider = MockProvider(
        responses=[tool_response, tool_response, tool_response, final_response]
    )

    search_tool = Tool(
        name="search",
        description="search",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        execute=execute_search,
    )

    result = await react_loop(
        provider,
        "find things",
        tools=[search_tool],
        max_rounds=8,
        max_history_messages=3,
    )

    assert executed == ["search", "search", "search"]
    assert result.metadata["tool_calls_made"] == 3
    assert result.metadata["messages_trimmed"] > 0
    for call_messages in provider.calls:
        assert len(call_messages.messages) <= 3, (
            f"Expected <=3 messages per call, got {len(call_messages.messages)}"
        )


async def test_react_loop_first_message_always_preserved() -> None:
    """After trimming, messages[0] always contains the original prompt."""

    executed: list[str] = []

    async def execute_search(**_: object) -> str:
        executed.append("search")
        return "ok"

    tool_response = _make_tool_response("search", "tc1", {"query": "x"})
    final_response = _make_final_response("Done")
    provider = MockProvider(
        responses=[tool_response, tool_response, tool_response, final_response]
    )

    search_tool = Tool(
        name="search",
        description="search",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        execute=execute_search,
    )

    result = await react_loop(
        provider,
        "original prompt",
        tools=[search_tool],
        max_rounds=8,
        max_history_messages=3,
    )

    assert executed == ["search", "search", "search"]
    assert result.metadata["messages_trimmed"] > 0
    for call_messages in provider.calls:
        assert call_messages.messages[0]["content"] == "original prompt"


async def test_react_loop_no_trim_when_none() -> None:
    """Default max_history_messages=None does not trim messages."""

    executed: list[str] = []

    async def execute_search(**_: object) -> str:
        executed.append("search")
        return "ok"

    tool_response = _make_tool_response("search", "tc1", {"query": "x"})
    final_response = _make_final_response("Done")
    provider = MockProvider(responses=[tool_response, tool_response, final_response])

    search_tool = Tool(
        name="search",
        description="search",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        execute=execute_search,
    )

    result = await react_loop(provider, "test", tools=[search_tool], max_rounds=8)

    assert executed == ["search", "search"]
    assert result.metadata["tool_calls_made"] == 2
    assert result.metadata["messages_trimmed"] == 0
    # With 2 tool rounds, the final call should have > 3 messages (not trimmed)
    final_call = provider.calls[-1]
    assert len(final_call.messages) > 3, "Messages grow unbounded when trim disabled"


# ---------------------------------------------------------------------------
# _trim_messages unit tests
# ---------------------------------------------------------------------------


class TestTrimMessages:
    """Unit tests for the _trim_messages helper."""

    def _msgs(self, n: int) -> list[dict[str, Any]]:
        """Return a list of n distinct message dicts."""
        return [{"role": "user", "content": f"msg{i}"} for i in range(n)]

    def test_no_trim_when_within_limit(self) -> None:

        msgs = self._msgs(3)
        result = _trim_messages(msgs, 5)
        assert result is msgs  # same object — no copy needed

    def test_trim_keeps_first_and_recent(self) -> None:

        msgs = self._msgs(6)
        result = _trim_messages(msgs, 3)
        assert len(result) == 3
        assert result[0] is msgs[0]
        assert result[1] is msgs[4]
        assert result[2] is msgs[5]

    def test_max_messages_equal_to_length_no_trim(self) -> None:

        msgs = self._msgs(4)
        result = _trim_messages(msgs, 4)
        assert result is msgs

    def test_max_messages_one_returns_only_first(self) -> None:

        msgs = self._msgs(5)
        result = _trim_messages(msgs, 1)
        assert result == [msgs[0]]
        assert len(result) == 1

    def test_max_messages_one_single_element_list(self) -> None:

        msgs = self._msgs(1)
        result = _trim_messages(msgs, 1)
        assert result == [msgs[0]]

    def test_max_messages_zero_raises_value_error(self) -> None:

        msgs = self._msgs(3)
        with pytest.raises(ValueError, match="max_messages must be >= 1"):
            _trim_messages(msgs, 0)

    def test_negative_max_messages_raises_value_error(self) -> None:

        msgs = self._msgs(3)
        with pytest.raises(ValueError, match="max_messages must be >= 1"):
            _trim_messages(msgs, -5)

    def test_does_not_mutate_input(self) -> None:

        msgs = self._msgs(6)
        original_len = len(msgs)
        _trim_messages(msgs, 3)
        assert len(msgs) == original_len

    def test_trim_does_not_split_tool_call_pair(self) -> None:

        msgs = [
            {"role": "user", "content": "prompt"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "tc1"}]},
            {"role": "tool", "tool_call_id": "tc1", "content": "result"},
            {"role": "assistant", "content": "final"},
        ]
        result = _trim_messages(msgs, 3)
        assert result == [msgs[0], msgs[3]]

    def test_trim_keeps_complete_tool_block_when_it_fits(self) -> None:

        msgs = [
            {"role": "user", "content": "prompt"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "tc1"}]},
            {"role": "tool", "tool_call_id": "tc1", "content": "result"},
            {"role": "assistant", "content": "final"},
        ]
        result = _trim_messages(msgs, 4)
        assert result == msgs


# ---------------------------------------------------------------------------
# TerminationReason (EK-5)
# ---------------------------------------------------------------------------


class TestTerminationReason:
    """EK-5: react_loop must distinguish natural completion from iteration cap."""

    def _make_search_tool(self) -> Tool:
        async def _execute(query: str) -> str:
            return "result"

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

    async def test_natural_completion_sets_termination_reason_natural(self) -> None:
        """When LLM returns a final answer, termination_reason == NATURAL."""
        tool_resp = _make_tool_response("search", "tc1", {"query": "q"})
        final_resp = _make_final_response("done")
        provider = MockProvider(responses=[tool_resp, final_resp])
        tool = self._make_search_tool()

        result = await react_loop(provider, "question", tools=[tool])

        assert result.metadata["termination_reason"] is TerminationReason.NATURAL

    async def test_natural_completion_not_flagged_as_max_iterations(self) -> None:
        """Natural completion must NOT carry MAX_ITERATIONS in termination_reason."""
        provider = MockProvider(responses=[_make_final_response("immediate answer")])
        tool = self._make_search_tool()

        result = await react_loop(provider, "question", tools=[tool])

        actual = result.metadata["termination_reason"]
        assert actual is not TerminationReason.MAX_ITERATIONS

    async def test_max_rounds_sets_termination_reason_max_iterations(self) -> None:
        """When max_rounds exhausted, MaxIterationsError.metadata has MAX_ITERATIONS."""
        # 2 rounds, each requesting a tool call — loop never finishes naturally.
        tool_resp = _make_tool_response("search", "tc1", {"query": "q"})
        provider = MockProvider(responses=[tool_resp, tool_resp])
        tool = self._make_search_tool()

        with pytest.raises(MaxIterationsError) as exc_info:
            await react_loop(provider, "question", tools=[tool], max_rounds=2)

        err = exc_info.value
        assert err.metadata["termination_reason"] is TerminationReason.MAX_ITERATIONS

    async def test_max_rounds_not_flagged_as_natural(self) -> None:
        """When max_rounds is hit, the exception must NOT carry NATURAL."""
        tool_resp = _make_tool_response("search", "tc2", {"query": "x"})
        provider = MockProvider(responses=[tool_resp])
        tool = self._make_search_tool()

        with pytest.raises(MaxIterationsError) as exc_info:
            await react_loop(provider, "question", tools=[tool], max_rounds=1)

        err = exc_info.value
        assert err.metadata.get("termination_reason") is not TerminationReason.NATURAL

    async def test_termination_reason_is_string_comparable(self) -> None:
        """TerminationReason is a StrEnum — string comparison also works."""
        provider = MockProvider(responses=[_make_final_response("ok")])
        tool = self._make_search_tool()

        result = await react_loop(provider, "hi", tools=[tool])

        # StrEnum: TerminationReason.NATURAL == "natural"
        assert result.metadata["termination_reason"] == "natural"


# ---------------------------------------------------------------------------
# Security: PII/secret redaction in trace events (SEC-001)
# ---------------------------------------------------------------------------


class TestTraceArgRedaction:
    """Verify that tool_call_start trace events respect redact_trace_args."""

    def _make_search_tool(self) -> Tool:
        async def _execute(query: str, api_key: str = "") -> str:
            return "result"

        return Tool(
            name="search",
            description="Search with optional api_key",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "api_key": {"type": "string"},
                },
                "required": ["query"],
            },
            execute=_execute,
        )

    async def test_redact_trace_args_true_hides_values(self) -> None:
        """With redact_trace_args=True (default), sensitive argument values must
        not appear in tool_call_start trace events."""
        events: list[Any] = []

        async def trace_cb(event: Any) -> None:
            events.append(event)

        tool_call = _make_tool_response(
            "search",
            "tc1",
            {"query": "hello", "api_key": "SECRET-KEY-12345"},
        )
        final = _make_final_response("done")
        provider = MockProvider(responses=[tool_call, final])
        tool = self._make_search_tool()

        await react_loop(
            provider,
            "question",
            tools=[tool],
            trace=trace_cb,
            # redact_trace_args=True is the default
        )

        start_events = [e for e in events if e.kind == "tool_call_start"]
        assert start_events, "Expected at least one tool_call_start event"

        for event in start_events:
            args_in_payload = event.payload.get("arguments", {})
            # The sensitive value must NOT appear verbatim in the trace.
            assert "SECRET-KEY-12345" not in args_in_payload.values(), (
                "Sensitive argument value leaked into trace event payload"
            )
            # Keys should still be present so traces are debuggable.
            assert "query" in args_in_payload, (
                "Argument key 'query' missing from redacted trace payload"
            )
            assert "api_key" in args_in_payload, (
                "Argument key 'api_key' missing from redacted trace payload"
            )
            # Values should be the redaction sentinel.
            assert all(v == "[redacted]" for v in args_in_payload.values()), (
                "Expected all argument values to be '[redacted]'"
            )

    async def test_redact_trace_args_false_exposes_values(self) -> None:
        """With redact_trace_args=False, raw argument values appear in the trace."""
        events: list[Any] = []

        async def trace_cb(event: Any) -> None:
            events.append(event)

        tool_call = _make_tool_response(
            "search",
            "tc1",
            {"query": "hello", "api_key": "SECRET-KEY-12345"},
        )
        final = _make_final_response("done")
        provider = MockProvider(responses=[tool_call, final])
        tool = self._make_search_tool()

        await react_loop(
            provider,
            "question",
            tools=[tool],
            trace=trace_cb,
            redact_trace_args=False,
        )

        start_events = [e for e in events if e.kind == "tool_call_start"]
        assert start_events, "Expected at least one tool_call_start event"

        found_sensitive = any(
            "SECRET-KEY-12345" in str(e.payload.get("arguments", {}).values())
            for e in start_events
        )
        assert found_sensitive, (
            "With redact_trace_args=False, raw argument values should appear in trace"
        )


# ---------------------------------------------------------------------------
# Validation: max_observation_chars=0 raises ValueError (SEC-002)
# ---------------------------------------------------------------------------


async def test_react_loop_zero_max_observation_chars_raises() -> None:
    """react_loop must raise ValueError when max_observation_chars < 1.

    This branch in _validate_react_loop_args was previously untested.
    """
    provider = MockProvider(responses=[_make_final_response("ok")])

    with pytest.raises(ValueError, match="max_observation_chars must be >= 1"):
        await react_loop(
            provider,
            "question",
            tools=[],
            max_observation_chars=0,
        )


# ---------------------------------------------------------------------------
# Multi-turn conversation: messages= seeding + returned transcript
# ---------------------------------------------------------------------------


def _make_search_tool(return_value: str = "result") -> Tool:
    async def _execute(query: str) -> str:
        return return_value

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


class TestReactLoopConversation:
    async def test_messages_param_seeds_conversation(self) -> None:
        provider = MockProvider(responses=[_make_final_response("hello back")])
        history = [
            {"role": "system", "content": "be nice"},
            {"role": "user", "content": "hi"},
        ]

        result = await react_loop(provider, messages=history, tools=[])

        assert result.value == "hello back"
        assert provider.last_call is not None
        assert provider.last_call.messages[0] == {
            "role": "system",
            "content": "be nice",
        }

    async def test_transcript_returned_in_metadata(self) -> None:
        provider = MockProvider(responses=[_make_final_response("answer")])

        result = await react_loop(provider, "ask")

        transcript = result.metadata["messages"]
        assert isinstance(transcript, tuple)
        assert transcript[0] == {"role": "user", "content": "ask"}
        assert transcript[-1] == {"role": "assistant", "content": "answer"}

    async def test_transcript_can_continue_conversation(self) -> None:
        provider1 = MockProvider(responses=[_make_final_response("first")])
        result1 = await react_loop(provider1, "q1")

        history = [*result1.metadata["messages"], {"role": "user", "content": "q2"}]
        provider2 = MockProvider(responses=[_make_final_response("second")])
        result2 = await react_loop(provider2, messages=history)

        assert result2.value == "second"
        assert provider2.last_call is not None
        roles = [m["role"] for m in provider2.last_call.messages]
        assert roles == ["user", "assistant", "user"]

    async def test_caller_messages_not_mutated(self) -> None:
        provider = MockProvider(responses=[_make_final_response("ok")])
        history = [{"role": "user", "content": "hi"}]

        await react_loop(provider, messages=history)

        assert history == [{"role": "user", "content": "hi"}]

    async def test_transcript_records_tool_round(self) -> None:
        provider = MockProvider(
            responses=[
                _make_tool_response("search", "tc1", {"query": "hello"}),
                _make_final_response("done"),
            ]
        )

        result = await react_loop(provider, "find hello", tools=[_make_search_tool()])

        roles = [m["role"] for m in result.metadata["messages"]]
        # user -> assistant(tool_calls) -> tool(result) -> assistant(final)
        assert roles == ["user", "assistant", "tool", "assistant"]

    async def test_max_iterations_metadata_includes_transcript(self) -> None:
        # Always returns a tool call -> never terminates naturally.
        provider = MockProvider(
            responses=[_make_tool_response("search", "tc1", {"query": "x"})]
        )

        with pytest.raises(MaxIterationsError) as exc_info:
            await react_loop(provider, "go", tools=[_make_search_tool()], max_rounds=2)

        assert "messages" in exc_info.value.metadata
        assert isinstance(exc_info.value.metadata["messages"], tuple)

    async def test_prompt_and_messages_mutually_exclusive(self) -> None:
        provider = MockProvider(responses=[_make_final_response("x")])
        with pytest.raises(ValueError, match="not both"):
            await react_loop(
                provider, "hi", messages=[{"role": "user", "content": "hi"}]
            )

    async def test_requires_prompt_or_messages(self) -> None:
        provider = MockProvider(responses=[_make_final_response("x")])
        with pytest.raises(ValueError, match="requires either prompt or messages"):
            await react_loop(provider)

    async def test_empty_messages_rejected(self) -> None:
        provider = MockProvider(responses=[_make_final_response("x")])
        with pytest.raises(ValueError, match="non-empty"):
            await react_loop(provider, messages=[])

    async def test_unknown_kwarg_rejected(self) -> None:
        # The **_ sink was removed: unknown kwargs now raise TypeError instead of
        # being silently swallowed (fixes the silent messages= footgun).
        provider = MockProvider(responses=[_make_final_response("x")])
        with pytest.raises(TypeError):
            await react_loop(provider, "hi", **{"bogus_kwarg": 123})


# ---------------------------------------------------------------------------
# Checkpoint transcript + summarize-on-trim
# ---------------------------------------------------------------------------


class TestReactLoopCheckpointMessages:
    async def test_checkpoint_state_contains_transcript_messages(self) -> None:
        """on_checkpoint state must carry a 'messages' list mirroring the roles
        of the transcript built so far (user -> assistant(tool_calls) -> tool)."""
        states: list[dict[str, Any]] = []

        async def on_checkpoint(round_num: int, state: dict[str, Any]) -> None:
            states.append(state)

        provider = MockProvider(
            responses=[
                _make_tool_response("search", "tc1", {"query": "hello"}),
                _make_final_response("done"),
            ]
        )

        await react_loop(
            provider,
            "find hello",
            tools=[_make_search_tool()],
            on_checkpoint=on_checkpoint,
        )

        assert states, "Expected at least one checkpoint invocation"
        messages = states[0]["messages"]
        assert isinstance(messages, list)
        # Checkpoint fires after the tool round: user -> assistant -> tool.
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "tool"]


async def _summarize(msgs: Any) -> str:
    """Stub async summarizer recording how many messages it condensed."""
    return f"{len(msgs)} earlier msgs"


class TestReactLoopSummarizeOnTrim:
    def _trimming_provider(self) -> MockProvider:
        """Provider that drives three tool rounds then a final answer."""
        tool_response = _make_tool_response("search", "tc1", {"query": "x"})
        final_response = _make_final_response("Done")
        return MockProvider(
            responses=[tool_response, tool_response, tool_response, final_response]
        )

    async def test_summarizer_invoked_and_summary_injected(self) -> None:
        """When trimming drops messages and a summarizer is supplied, the summary
        appears as a system message in the provider's recorded call messages and
        metadata['summarized'] is incremented."""
        invoked: list[int] = []

        async def summ(msgs: Any) -> str:
            invoked.append(len(msgs))
            return f"{len(msgs)} earlier msgs"

        provider = self._trimming_provider()

        result = await react_loop(
            provider,
            "find things",
            tools=[_make_search_tool()],
            max_rounds=8,
            max_history_messages=3,
            summarizer=summ,
        )

        assert invoked, "summarizer must have been invoked at least once"
        assert result.metadata["summarized"] >= 1
        assert result.metadata["messages_trimmed"] >= 1

        # The injected summary must reach the provider as a system message.
        system_contents = [
            m["content"]
            for call in provider.calls
            for m in call.messages
            if m.get("role") == "system"
        ]
        assert any("earlier msgs" in content for content in system_contents), (
            "Expected the summary text to appear as a system message"
        )
        assert any(
            content.startswith("Summary of earlier conversation: ")
            for content in system_contents
        )

    async def test_no_summary_when_summarizer_none(self) -> None:
        """With summarizer=None and trimming active, no system summary message is
        injected and metadata['summarized'] stays 0."""
        provider = self._trimming_provider()

        result = await react_loop(
            provider,
            "find things",
            tools=[_make_search_tool()],
            max_rounds=8,
            max_history_messages=3,
        )

        assert result.metadata["messages_trimmed"] >= 1
        assert result.metadata["summarized"] == 0
        system_msgs = [
            m
            for call in provider.calls
            for m in call.messages
            if m.get("role") == "system"
        ]
        assert system_msgs == [], "No system summary message should be injected"

    async def test_stored_transcript_unaffected_by_summarization(self) -> None:
        """Summarization only touches the per-round window; the stored transcript
        in metadata['messages'] must remain the full history with no injected
        summary system message."""
        provider = self._trimming_provider()

        result = await react_loop(
            provider,
            "find things",
            tools=[_make_search_tool()],
            max_rounds=8,
            max_history_messages=3,
            summarizer=_summarize,
        )

        transcript = result.metadata["messages"]
        roles = [m["role"] for m in transcript]
        # Three tool rounds then a final answer; no 'system' summary leaks in.
        assert "system" not in roles
        assert roles == [
            "user",
            "assistant",
            "tool",
            "assistant",
            "tool",
            "assistant",
            "tool",
            "assistant",
        ]
