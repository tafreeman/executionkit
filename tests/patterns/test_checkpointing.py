"""Tests for in-loop checkpointing in refine_loop and react_loop (Item C)."""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any

from executionkit._mock import MockProvider
from executionkit.patterns.react_loop import react_loop
from executionkit.patterns.refine_loop import refine_loop
from executionkit.provider import LLMResponse, ToolCall
from executionkit.types import PatternResult, Tool

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _tool_response(name: str, call_id: str, args: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        content="",
        finish_reason="tool_calls",
        tool_calls=(ToolCall(id=call_id, name=name, arguments=args),),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
    )


def _final_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        finish_reason="stop",
        tool_calls=(),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
    )


def _search_tool() -> Tool:
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


def _fixed_scores(values: list[float]) -> Any:
    """Build a custom evaluator that yields the given scores in order.

    A custom evaluator makes no provider calls, so generation calls are the only
    source of cost — handy for asserting per-checkpoint spend.
    """
    scores = iter(values)

    async def _evaluator(text: str, llm: Any) -> float:
        return next(scores)

    return _evaluator


# ---------------------------------------------------------------------------
# refine_loop
# ---------------------------------------------------------------------------


async def test_refine_loop_checkpoint_called_per_iteration() -> None:
    provider = MockProvider(responses=["gen0", "gen1", "gen2", "gen3"])
    seen: list[int] = []

    def on_checkpoint(index: int, state: dict[str, Any]) -> None:
        seen.append(index)

    await refine_loop(
        provider,
        "prompt",
        evaluator=_fixed_scores([0.1, 0.2, 0.3, 0.4]),
        target_score=0.99,
        max_iterations=3,
        patience=10,
        on_checkpoint=on_checkpoint,
    )
    # initial generation (0) + 3 refinement iterations (1, 2, 3)
    assert seen == [0, 1, 2, 3]


async def test_cost_in_checkpoint_reflects_spend_to_that_point() -> None:
    provider = MockProvider(responses=["a", "b", "c"])
    llm_calls_seen: list[int] = []

    def on_checkpoint(index: int, state: dict[str, Any]) -> None:
        llm_calls_seen.append(state["cost"]["llm_calls"])

    await refine_loop(
        provider,
        "prompt",
        evaluator=_fixed_scores([0.1, 0.2, 0.3]),
        target_score=0.99,
        max_iterations=2,
        patience=10,
        on_checkpoint=on_checkpoint,
    )
    # Custom evaluator makes no provider calls, so llm_calls == generations so far.
    assert llm_calls_seen == [1, 2, 3]


async def test_async_checkpoint_callback_is_awaited() -> None:
    provider = MockProvider(responses=["a", "b"])
    awaited: list[int] = []

    async def on_checkpoint(index: int, state: dict[str, Any]) -> None:
        awaited.append(index)

    await refine_loop(
        provider,
        "prompt",
        evaluator=_fixed_scores([0.1, 0.2]),
        target_score=0.99,
        max_iterations=1,
        patience=10,
        on_checkpoint=on_checkpoint,
    )
    # If the coroutine were not awaited, nothing would be appended.
    assert awaited == [0, 1]


async def test_sync_checkpoint_callback_works() -> None:
    provider = MockProvider(responses=["a", "b"])
    seen: list[int] = []

    def on_checkpoint(index: int, state: dict[str, Any]) -> None:
        seen.append(index)

    await refine_loop(
        provider,
        "prompt",
        evaluator=_fixed_scores([0.1, 0.2]),
        target_score=0.99,
        max_iterations=1,
        patience=10,
        on_checkpoint=on_checkpoint,
    )
    assert seen == [0, 1]


async def test_checkpoint_failure_does_not_abort_loop() -> None:
    provider = MockProvider(responses=["a", "b", "c", "d"])
    calls: list[int] = []

    def on_checkpoint(index: int, state: dict[str, Any]) -> None:
        calls.append(index)
        raise RuntimeError("boom")

    result = await refine_loop(
        provider,
        "prompt",
        evaluator=_fixed_scores([0.1, 0.2, 0.3, 0.4]),
        target_score=0.99,
        max_iterations=3,
        patience=10,
        on_checkpoint=on_checkpoint,
    )
    # Every checkpoint raised, yet the loop ran to completion.
    assert isinstance(result, PatternResult)
    assert calls == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# react_loop
# ---------------------------------------------------------------------------


async def test_react_loop_checkpoint_called_per_round() -> None:
    provider = MockProvider(
        responses=[
            _tool_response("search", "t1", {"query": "a"}),
            _tool_response("search", "t2", {"query": "b"}),
            _final_response("done"),
        ]
    )
    seen: list[int] = []

    def on_checkpoint(index: int, state: dict[str, Any]) -> None:
        seen.append(index)

    await react_loop(
        provider, "go", tools=[_search_tool()], on_checkpoint=on_checkpoint
    )
    # Two rounds dispatched tool calls (0, 1); the final-answer round returns first.
    assert seen == [0, 1]


# ---------------------------------------------------------------------------
# JSON-serializability across both patterns
# ---------------------------------------------------------------------------


async def test_checkpoint_state_is_json_serializable() -> None:
    refine_states: list[dict[str, Any]] = []

    def refine_cb(index: int, state: dict[str, Any]) -> None:
        json.dumps(state)  # must not raise
        refine_states.append(state)

    await refine_loop(
        MockProvider(responses=["a", "b"]),
        "prompt",
        evaluator=_fixed_scores([0.1, 0.2]),
        target_score=0.99,
        max_iterations=1,
        patience=10,
        on_checkpoint=refine_cb,
    )
    assert refine_states
    assert set(refine_states[0]) == {
        "iteration",
        "current_text",
        "current_score",
        "cost",
    }

    react_states: list[dict[str, Any]] = []

    def react_cb(index: int, state: dict[str, Any]) -> None:
        json.dumps(state)  # must not raise
        react_states.append(state)

    await react_loop(
        MockProvider(
            responses=[
                _tool_response("search", "t1", {"query": "a"}),
                _final_response("done"),
            ]
        ),
        "go",
        tools=[_search_tool()],
        on_checkpoint=react_cb,
    )
    assert react_states
    assert set(react_states[0]) == {
        "round",
        "last_response",
        "tool_calls_made",
        "cost",
        "messages",
    }
