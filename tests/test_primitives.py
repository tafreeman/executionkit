"""Tests for lightweight public orchestration primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from executionkit._mock import MockProvider
from executionkit.provider import LLMResponse, ToolCall
from executionkit.types import PatternResult, TokenUsage, Tool

if TYPE_CHECKING:
    from executionkit.observability import TraceEvent


async def test_consensus_emits_trace_events() -> None:
    from executionkit.patterns.consensus import consensus

    events: list[TraceEvent] = []

    async def trace(event: TraceEvent) -> None:
        events.append(event)

    result = await consensus(
        MockProvider(responses=["answer"]),
        "question",
        num_samples=1,
        trace=trace,
    )

    assert result.value == "answer"
    assert [event.kind for event in events] == ["llm_call_start", "llm_call_end"]
    assert events[-1].payload["cost"].llm_calls == 1


async def test_structured_and_refine_emit_trace_events() -> None:
    from executionkit.patterns.refine_loop import refine_loop
    from executionkit.patterns.structured import structured

    events: list[TraceEvent] = []

    def trace(event: TraceEvent) -> None:
        events.append(event)

    async def evaluator(value: str, provider: object) -> float:
        return 1.0

    structured_result = await structured(
        MockProvider(responses=['{"ok": true}']),
        "json",
        trace=trace,
    )
    refine_result = await refine_loop(
        MockProvider(responses=["answer"]),
        "improve",
        evaluator=evaluator,
        trace=trace,
    )

    assert structured_result.value == {"ok": True}
    assert refine_result.value == "answer"
    assert [event.kind for event in events].count("llm_call_end") == 2


async def test_router_selects_matching_rule_and_fallback() -> None:
    from executionkit.patterns.consensus import consensus
    from executionkit.routing import Router, RouteRule

    cheap = MockProvider(responses=["cheap"])
    premium = MockProvider(responses=["premium"])
    router = Router(
        rules=[
            RouteRule(
                name="long-prompts",
                provider=premium,
                predicate=lambda prompt, context: (
                    len(prompt) > 10 or context.get("tier") == "premium"
                ),
            )
        ],
        fallback=cheap,
    )

    assert router.select("short") is cheap
    assert router.select("short", tier="premium") is premium
    assert router.select("this prompt is long") is premium

    result = await router.run(consensus, "this prompt is long", num_samples=1)
    assert result.value == "premium"


async def test_router_run_separates_context_from_pattern_kwargs() -> None:
    """run() routes via ``context=`` and forwards ``**kwargs`` only to the
    pattern, so a routing key (e.g. ``tier``) cannot leak into the pattern call
    and raise ``TypeError``."""
    from executionkit.patterns.consensus import consensus
    from executionkit.routing import Router, RouteRule

    cheap = MockProvider(responses=["cheap"])
    premium = MockProvider(responses=["premium"])
    router = Router(
        rules=[
            RouteRule(
                name="premium-tier",
                provider=premium,
                predicate=lambda prompt, context: context.get("tier") == "premium",
            )
        ],
        fallback=cheap,
    )

    # ``tier`` routes (via context) but is NOT forwarded to consensus, which has
    # no ``tier`` parameter — a leak would raise TypeError on this call. A stray
    # ``prompt`` key is also present to prove it does not collide with the
    # positional ``prompt`` passed to ``select``.
    routed = await router.run(
        consensus,
        "short",
        context={"tier": "premium", "prompt": "ignored"},
        num_samples=1,
    )
    assert routed.value == "premium"

    # Without routing context, the same short prompt falls back.
    fell_back = await router.run(consensus, "short", num_samples=1)
    assert fell_back.value == "cheap"


async def test_workflow_runs_branching_steps_and_aggregates_cost() -> None:
    from executionkit.workflow import Step, Workflow

    async def root(context: dict[str, Any]) -> PatternResult[str]:
        return PatternResult("root", cost=TokenUsage(llm_calls=1))

    async def branch_a(context: dict[str, Any]) -> str:
        return f"{context['root']}:a"

    async def branch_b(context: dict[str, Any]) -> str:
        return f"{context['root']}:b"

    workflow = Workflow(
        [
            Step("root", root),
            Step("branch_a", branch_a, depends_on=("root",)),
            Step("branch_b", branch_b, depends_on=("root",)),
        ]
    )

    result = await workflow.run()

    assert result.outputs == {
        "root": "root",
        "branch_a": "root:a",
        "branch_b": "root:b",
    }
    assert result.cost.llm_calls == 1


async def test_workflow_approval_gate_blocks_and_allows_steps() -> None:
    from executionkit.approval import ApprovalDeniedError, ApprovalGate
    from executionkit.workflow import Step, Workflow

    executed: list[str] = []

    async def side_effect(context: dict[str, Any]) -> str:
        executed.append("side-effect")
        return "ran"

    workflow = Workflow([Step("side_effect", side_effect)])

    with pytest.raises(ApprovalDeniedError, match="needs review"):
        await workflow.run(approval_gate=ApprovalGate.deny_all("needs review"))

    assert executed == []

    result = await workflow.run(approval_gate=ApprovalGate.allow_all())

    assert executed == ["side-effect"]
    assert result.outputs["side_effect"] == "ran"


async def test_plan_executes_steps_in_order() -> None:
    from executionkit.planning import Plan, PlanStep

    plan = Plan(
        [
            PlanStep("draft", "create draft", lambda context: "draft"),
            PlanStep(
                "review",
                "review draft",
                lambda context: context["draft"] + ":ok",
            ),
        ]
    )

    result = await plan.execute()

    assert result.outputs == {"draft": "draft", "review": "draft:ok"}


async def test_approval_gate_blocks_react_tool_execution() -> None:
    from executionkit.approval import ApprovalDecision, ApprovalGate
    from executionkit.patterns.react_loop import react_loop

    executed: list[str] = []

    async def execute_search(query: str) -> str:
        executed.append(query)
        return "found"

    tool = Tool(
        name="search",
        description="search",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        execute=execute_search,
    )
    provider = MockProvider(
        responses=[
            LLMResponse(
                content="",
                tool_calls=(ToolCall("tc1", "search", {"query": "secret"}),),
            ),
            LLMResponse(content="done"),
        ]
    )
    gate = ApprovalGate(
        lambda request: ApprovalDecision(approved=False, reason="needs review")
    )

    result = await react_loop(provider, "find", [tool], approval_gate=gate)

    assert result.value == "done"
    assert executed == []
    tool_messages = [
        message["content"]
        for message in provider.calls[1].messages
        if message["role"] == "tool"
    ]
    assert "blocked by approval" in tool_messages[0]
    assert "needs review" in tool_messages[0]


async def test_workflow_cycle_raises_execution_kit_error() -> None:
    """A dependency cycle (a→b, b→a) must never resolve; the deadlock branch
    at workflow.py:106 raises ExecutionKitError rather than looping forever."""
    from executionkit.errors import ExecutionKitError
    from executionkit.workflow import Step, Workflow

    workflow = Workflow(
        [
            Step("a", lambda ctx: "a", depends_on=("b",)),
            Step("b", lambda ctx: "b", depends_on=("a",)),
        ]
    )

    with pytest.raises(ExecutionKitError, match="could not be resolved"):
        await workflow.run()


async def test_workflow_orphan_dep_raises_execution_kit_error() -> None:
    """An orphaned dependency that passes _validate (because the dep step
    exists) but can never become ready because its own dep is in the cycle."""
    from executionkit.errors import ExecutionKitError
    from executionkit.workflow import Step, Workflow

    # "root" runs fine; "a" depends on "b" which depends on "a" — two steps
    # are permanently stuck even though they are known step names.
    workflow = Workflow(
        [
            Step("root", lambda ctx: "root"),
            Step("a", lambda ctx: "a", depends_on=("b",)),
            Step("b", lambda ctx: "b", depends_on=("a",)),
        ]
    )

    # root completes, then the pending set {a, b} cannot be resolved.
    with pytest.raises(ExecutionKitError, match="could not be resolved"):
        await workflow.run()


async def test_approval_gate_allows_react_tool_execution() -> None:
    from executionkit.approval import ApprovalDecision, ApprovalGate
    from executionkit.patterns.react_loop import react_loop

    executed: list[str] = []

    async def execute_search(query: str) -> str:
        executed.append(query)
        return "found"

    tool = Tool(
        name="search",
        description="search",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        execute=execute_search,
    )
    provider = MockProvider(
        responses=[
            LLMResponse(
                content="",
                tool_calls=(ToolCall("tc1", "search", {"query": "public"}),),
            ),
            LLMResponse(content="done"),
        ]
    )
    gate = ApprovalGate(lambda request: ApprovalDecision(approved=True))

    await react_loop(provider, "find", [tool], approval_gate=gate)

    assert executed == ["public"]
