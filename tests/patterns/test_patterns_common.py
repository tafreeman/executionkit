"""Cross-pattern and base-layer tests that don't belong to a single pattern.

Covers:
- patterns/base.py: validate_score, _note_truncation, _TrackedProvider,
  checked_complete, _check_budget
- TestPatternInputValidation: input validation spanning consensus, refine_loop,
  react_loop, and _execute_tool_call
- TestTrackedProviderSupportsDelegation: capability delegation
- test_tool_error_leaks_only_type: security contract (react_loop adjacent)
- test_no_await_between_check_and_reserve: AST-based concurrency guard

These tests were not cleanly attributable to a single pattern in the original
monolithic file and are collected here rather than being silently dropped.
"""

from __future__ import annotations

import ast
import textwrap
import warnings
from types import MappingProxyType

import pytest

from executionkit._mock import MockProvider
from executionkit.cost import CostTracker
from executionkit.engine.retry import RetryConfig
from executionkit.errors import BudgetExhaustedError
from executionkit.patterns.base import (
    BUDGET_EXHAUSTED_SENTINEL,
    _check_budget,
    _note_truncation,
    _TrackedProvider,
    checked_complete,
    validate_score,
)
from executionkit.patterns.consensus import consensus
from executionkit.patterns.react_loop import _execute_tool_call, react_loop
from executionkit.patterns.refine_loop import refine_loop
from executionkit.provider import (
    LLMResponse,
    ProviderError,
    ToolCall,
)
from executionkit.types import TokenUsage, Tool

# ---------------------------------------------------------------------------
# Local response builders (duplicated from test_react_loop for self-containment)
# ---------------------------------------------------------------------------


def _make_tool_response(tool_name: str, tool_id: str, args: dict) -> LLMResponse:
    return LLMResponse(
        content="",
        finish_reason="tool_calls",
        tool_calls=(ToolCall(id=tool_id, name=tool_name, arguments=args),),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 5}),
    )


def _make_final_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        finish_reason="stop",
        tool_calls=(),
        usage=MappingProxyType({"prompt_tokens": 10, "completion_tokens": 20}),
    )


# ---------------------------------------------------------------------------
# base.py coverage: validate_score, _note_truncation, _TrackedProvider
# ---------------------------------------------------------------------------


def test_validate_score_raises_on_nan() -> None:
    from math import nan

    with pytest.raises(ValueError, match="Invalid evaluator score"):
        validate_score(nan)


def test_validate_score_raises_on_out_of_range() -> None:

    with pytest.raises(ValueError):
        validate_score(1.5)


async def test_note_truncation_emits_warning() -> None:
    """_note_truncation should warn and increment counter when truncated."""

    response = LLMResponse(
        content="hi",
        usage=MappingProxyType({"prompt_tokens": 1, "completion_tokens": 1}),
        finish_reason="length",
    )
    meta: dict[str, object] = {}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _note_truncation(response, meta, "test_pattern")

    assert meta["truncated_responses"] == 1
    assert len(w) == 1
    assert "truncated" in str(w[0].message).lower()


async def test_tracked_provider_delegates_and_tracks() -> None:
    """_TrackedProvider.complete must delegate and record usage."""

    provider = MockProvider(responses=["hello"])
    tracker = CostTracker()
    meta: dict[str, object] = {}

    tracked = _TrackedProvider(
        provider,
        tracker,
        meta,
        budget=None,
        retry=None,
        context="test",
    )
    response = await tracked.complete([{"role": "user", "content": "hi"}])
    assert response.content == "hello"
    assert tracker.call_count == 1


async def test_checked_complete_raises_on_input_token_budget() -> None:
    """checked_complete must raise BudgetExhaustedError when input tokens exhausted."""

    provider = MockProvider(responses=["x"])
    tracker = CostTracker()
    # Pre-fill tracker with usage exceeding budget
    tracker.add_usage(TokenUsage(input_tokens=100, output_tokens=0, llm_calls=1))
    budget = TokenUsage(input_tokens=50, output_tokens=0, llm_calls=0)

    msgs = [{"role": "user", "content": "hi"}]
    with pytest.raises(BudgetExhaustedError, match="Input token"):
        await checked_complete(provider, msgs, tracker, budget, None)


async def test_checked_complete_counts_failed_wire_attempts() -> None:
    """Failed retries still count real wire attempts in the tracker."""

    class FailingProvider:
        async def complete(self, messages: object, **kwargs: object) -> object:
            raise ProviderError("network down")

    provider = FailingProvider()  # type: ignore[arg-type]
    tracker = CostTracker()

    msgs = [{"role": "user", "content": "hi"}]
    with pytest.raises(ProviderError):
        await checked_complete(
            provider,
            msgs,
            tracker,
            None,
            RetryConfig(max_retries=3, base_delay=0.0),
        )

    assert tracker.call_count == 3


async def test_checked_complete_stops_retry_when_call_budget_exhausted() -> None:
    """Call budgets must stop retry dispatch once the attempt limit is reached."""

    class FailingProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, messages: object, **kwargs: object) -> object:
            self.calls += 1
            raise ProviderError("network down")

    provider = FailingProvider()  # type: ignore[arg-type]
    tracker = CostTracker()
    budget = TokenUsage(llm_calls=1)

    with pytest.raises(BudgetExhaustedError, match="before retry dispatch"):
        await checked_complete(
            provider,
            [{"role": "user", "content": "hi"}],
            tracker,
            budget,
            RetryConfig(max_retries=3, base_delay=0.0),
        )

    assert provider.calls == 1
    assert tracker.call_count == 1


# ---------------------------------------------------------------------------
# Input validation spanning multiple patterns
# ---------------------------------------------------------------------------


class TestPatternInputValidation:
    async def test_consensus_rejects_invalid_max_concurrency(self) -> None:

        provider = MockProvider(responses=["ok"])
        with pytest.raises(ValueError, match="max_concurrency must be >= 1"):
            await consensus(provider, "hi", max_concurrency=0)

    async def test_consensus_rejects_invalid_max_tokens(self) -> None:

        provider = MockProvider(responses=["ok"])
        with pytest.raises(ValueError, match="max_tokens must be >= 1"):
            await consensus(provider, "hi", max_tokens=0)

    async def test_refine_loop_rejects_invalid_target_score(self) -> None:

        provider = MockProvider(responses=["ok"])
        with pytest.raises(ValueError, match="target_score must be in"):
            await refine_loop(provider, "hi", target_score=1.5)

    async def test_refine_loop_rejects_invalid_patience(self) -> None:

        provider = MockProvider(responses=["ok"])
        with pytest.raises(ValueError, match="patience must be >= 1"):
            await refine_loop(provider, "hi", patience=0)

    async def test_refine_loop_rejects_invalid_max_eval_chars(self) -> None:

        provider = MockProvider(responses=["ok"])
        with pytest.raises(ValueError, match="max_eval_chars must be >= 1"):
            await refine_loop(provider, "hi", max_eval_chars=0)

    async def test_react_loop_rejects_invalid_max_rounds(self) -> None:

        provider = MockProvider(responses=[_make_final_response("done")])
        with pytest.raises(ValueError, match="max_rounds must be >= 1"):
            await react_loop(provider, "hi", tools=[], max_rounds=0)

    async def test_react_loop_rejects_invalid_tool_timeout(self) -> None:

        provider = MockProvider(responses=[_make_final_response("done")])
        with pytest.raises(ValueError, match="tool_timeout must be > 0"):
            await react_loop(provider, "hi", tools=[], tool_timeout=0)

    async def test_react_loop_rejects_invalid_history_limit(self) -> None:

        provider = MockProvider(responses=[_make_final_response("done")])
        with pytest.raises(ValueError, match="max_history_messages must be >= 1"):
            await react_loop(provider, "hi", tools=[], max_history_messages=0)

    async def test_react_loop_truncates_small_limit(self) -> None:

        async def tool_fn() -> str:
            return "abcdef"

        tool = Tool(
            name="tiny",
            description="tiny",
            parameters={"type": "object", "properties": {}},
            execute=tool_fn,
        )
        result = await _execute_tool_call(
            tc_name="tiny",
            tc_arguments={},
            tool_lookup={"tiny": tool},
            tool_timeout=None,
            max_observation_chars=1,
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# P2-SEC-08: _execute_tool_call leaks only exception type, not message
# ---------------------------------------------------------------------------


async def test_tool_error_leaks_only_type() -> None:
    """Tool exceptions must expose only the type name — not the message — to the LLM."""

    async def leaky_execute(query: str) -> str:
        raise ValueError("password=hunter2")

    leaky_tool = Tool(
        name="leaky",
        description="A tool that leaks secrets in its exception message",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        execute=leaky_execute,
    )

    tool_call = _make_tool_response("leaky", "tc1", {"query": "test"})
    final = _make_final_response("Handled the error")

    provider = MockProvider(responses=[tool_call, final])
    await react_loop(provider, "question", tools=[leaky_tool])

    # Inspect the tool-role message that was fed back to the second LLM call
    second_call_messages = provider.calls[1].messages
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert tool_msgs, "Expected at least one tool observation message"
    observation = tool_msgs[0]["content"]

    assert "hunter2" not in observation
    assert "ValueError" in observation


# ---------------------------------------------------------------------------
# _check_budget regression tests (F-05)
# Ref: field-loop pattern from CPython dataclasses.asdict() eliminates
# per-field if-chain repetition.
# ---------------------------------------------------------------------------


class TestCheckBudget:
    """_check_budget raises BudgetExhaustedError on the first exceeded field."""

    def test_no_error_when_all_limits_zero(self) -> None:
        """0 is the unlimited sentinel — should never raise."""

        _check_budget(
            TokenUsage(llm_calls=0, input_tokens=0, output_tokens=0),
            TokenUsage(llm_calls=999, input_tokens=999, output_tokens=999),
            ("llm_calls", "input_tokens", "output_tokens"),
            sentinel_suffix="(pipe)",
            exceeded_suffix="before dispatch",
        )

    def test_raises_on_call_limit_hit(self) -> None:

        with pytest.raises(BudgetExhaustedError) as exc_info:
            _check_budget(
                TokenUsage(llm_calls=3, input_tokens=0, output_tokens=0),
                TokenUsage(llm_calls=3, input_tokens=100, output_tokens=100),
                ("llm_calls", "input_tokens", "output_tokens"),
                sentinel_suffix="(pipe)",
                exceeded_suffix="before dispatch",
            )
        assert "LLM call" in str(exc_info.value)
        assert "before dispatch" in str(exc_info.value)

    def test_raises_on_sentinel_minus_one(self) -> None:

        with pytest.raises(BudgetExhaustedError) as exc_info:
            _check_budget(
                TokenUsage(
                    llm_calls=BUDGET_EXHAUSTED_SENTINEL,
                    input_tokens=0,
                    output_tokens=0,
                ),
                TokenUsage(llm_calls=0, input_tokens=0, output_tokens=0),
                ("llm_calls",),
                sentinel_suffix="before retry (forwarded from pipe)",
                exceeded_suffix="before retry dispatch",
            )
        assert "forwarded from pipe" in str(exc_info.value)

    def test_raises_on_input_token_limit(self) -> None:

        # llm_calls=0 means unlimited; only input_tokens limit is set.
        # current input_tokens (500) exceeds budget (100) → Input token error.
        with pytest.raises(BudgetExhaustedError) as exc_info:
            _check_budget(
                TokenUsage(llm_calls=0, input_tokens=100, output_tokens=0),
                TokenUsage(llm_calls=10, input_tokens=500, output_tokens=500),
                ("llm_calls", "input_tokens", "output_tokens"),
                sentinel_suffix="(pipe)",
                exceeded_suffix="before dispatch",
            )
        assert "Input token" in str(exc_info.value)

    def test_error_carries_cost_and_budget_metadata(self) -> None:

        budget = TokenUsage(llm_calls=1, input_tokens=0, output_tokens=0)
        current = TokenUsage(llm_calls=1, input_tokens=0, output_tokens=0)
        with pytest.raises(BudgetExhaustedError) as exc_info:
            _check_budget(
                budget,
                current,
                ("llm_calls",),
                sentinel_suffix="(pipe)",
                exceeded_suffix="before dispatch",
            )
        assert exc_info.value.cost == current
        assert exc_info.value.metadata["budget"] == budget


# ---------------------------------------------------------------------------
# _TrackedProvider.supports_tools delegation tests (F-04)
# Ref: @runtime_checkable only checks presence, not value — a wrapper must
# delegate the capability flag to the inner provider.
# PEP 544: https://peps.python.org/pep-0544/
# ---------------------------------------------------------------------------


class TestTrackedProviderSupportsDelegation:
    """_TrackedProvider.supports_tools delegates to the wrapped provider."""

    def test_delegates_true_from_tool_capable_provider(self) -> None:

        inner = MockProvider(responses=["ok"])
        # MockProvider has supports_tools = True
        tp = _TrackedProvider(
            inner,
            CostTracker(),
            {},
            budget=None,
            retry=None,
            context="test",
        )
        assert tp.supports_tools is True

    def test_delegates_false_from_non_tool_provider(self) -> None:
        """A plain LLMProvider without supports_tools must yield False."""

        class MinimalProvider:
            async def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
                return LLMResponse(content="ok")

        tp = _TrackedProvider(
            MinimalProvider(),  # type: ignore[arg-type]
            CostTracker(),
            {},
            budget=None,
            retry=None,
            context="test",
        )
        assert tp.supports_tools is False


# ---------------------------------------------------------------------------
# FIX #4: CostTracker concurrency model — no-await ordering regression test.
#
# The budget check (_check_budget) and call reservation (reserve_call) in
# checked_complete's _before_attempt closure must remain in the same
# synchronous run-segment with no ``await`` between them.  If an await is
# inserted between them, concurrent asyncio coroutines sharing a CostTracker
# could both pass the budget check before either has incremented the counter,
# causing the budget to be overshot.
#
# This test uses inspect.getsource to statically assert the ordering
# invariant.  It will fail CI if an await is accidentally introduced.
# ---------------------------------------------------------------------------


def test_no_await_between_check_and_reserve() -> None:
    """No ``await`` must appear between _check_budget and reserve_call() in
    checked_complete's _before_attempt closure.

    This is an AST-based regression test that guards the asyncio budget-safety
    guarantee documented in executionkit/cost.py and
    executionkit/patterns/base.py.  If this test fails after a refactor,
    re-evaluate the concurrency contract before merging.

    The visitor walks the _before_attempt AsyncFunctionDef in source order and
    records events for each _check_budget call ("check"), each .reserve_call()
    call ("reserve"), and any Await node ("await").  It then asserts:
      - at least one "check" and exactly one "reserve" are present,
      - the first "check" precedes "reserve",
      - no "await" appears between the first "check" and "reserve".

    With two _check_budget branches (attempt==1 and else) before a single
    reserve_call(), the event list looks like [check, check, reserve, await...]
    which satisfies all assertions.
    """
    import inspect

    source = inspect.getsource(checked_complete)

    # Parse the full checked_complete source into an AST.
    # dedent first so the nested function parses cleanly as a module.
    tree = ast.parse(textwrap.dedent(source))

    # Locate the _before_attempt AsyncFunctionDef node.
    before_attempt_node: ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_before_attempt":
            before_attempt_node = node
            break

    assert before_attempt_node is not None, (
        "_before_attempt closure not found in checked_complete source"
    )

    class _OrderedEventVisitor(ast.NodeVisitor):
        """Walk AST in source order, recording check/reserve/await events."""

        def __init__(self) -> None:
            self.events: list[str] = []

        def visit_Call(self, node: ast.Call) -> None:
            # _check_budget(...) — bare name call
            if isinstance(node.func, ast.Name) and node.func.id == "_check_budget":
                self.events.append("check")
            # tracker.reserve_call() — attribute call ending in reserve_call
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "reserve_call"
            ):
                self.events.append("reserve")
            self.generic_visit(node)

        def visit_Await(self, node: ast.Await) -> None:
            self.events.append("await")
            self.generic_visit(node)

    visitor = _OrderedEventVisitor()
    visitor.visit(before_attempt_node)
    events = visitor.events

    assert "reserve" in events, (
        "reserve_call() not found inside _before_attempt closure"
    )
    assert "check" in events, "_check_budget() not found inside _before_attempt closure"

    first_check_idx = events.index("check")
    reserve_idx = events.index("reserve")

    assert first_check_idx < reserve_idx, (
        "_check_budget() must appear before reserve_call() in _before_attempt"
    )

    # No await must appear between the first check and the reserve.
    between_events = events[first_check_idx:reserve_idx]
    assert "await" not in between_events, (
        "An ``await`` was found between _check_budget and reserve_call() in "
        "checked_complete._before_attempt.  This breaks the asyncio budget-safety "
        "guarantee — no other coroutine must be schedulable between the budget check "
        "and the call reservation.  See executionkit/cost.py module docstring."
    )
