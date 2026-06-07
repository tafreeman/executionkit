"""Plan-then-execute primitives."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from executionkit.approval import ApprovalGate, ApprovalRequest
from executionkit.observability import TraceCallback, TraceEvent, emit_trace
from executionkit.types import PatternResult, TokenUsage

PlanRun: TypeAlias = Callable[[dict[str, Any]], Awaitable[Any] | Any]


@dataclass(frozen=True, slots=True)
class PlanStep:
    """A human-readable executable plan step."""

    name: str
    instruction: str
    run: PlanRun
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanResult:
    """Outputs and aggregate cost from plan execution."""

    outputs: MappingProxyType[str, Any]
    cost: TokenUsage = field(default_factory=TokenUsage)


class Plan:
    """Execute named plan steps in order."""

    def __init__(self, steps: Sequence[PlanStep]) -> None:
        names = [step.name for step in steps]
        if len(names) != len(set(names)):
            raise ValueError("Plan step names must be unique")
        self.steps = tuple(steps)

    async def execute(
        self,
        initial_context: Mapping[str, Any] | None = None,
        *,
        trace: TraceCallback | None = None,
        approval_gate: ApprovalGate | None = None,
    ) -> PlanResult:
        outputs: dict[str, Any] = dict(initial_context or {})
        total_cost = TokenUsage()

        for step in self.steps:
            if approval_gate is not None:
                await approval_gate.require(
                    ApprovalRequest.create(
                        "plan_step",
                        step.name,
                        {"instruction": step.instruction, **dict(step.metadata)},
                    )
                )
            await emit_trace(
                trace,
                TraceEvent.create("plan_step_start", {"step": step.name}),
            )
            maybe_output = step.run(dict(outputs))
            output = (
                await maybe_output
                if inspect.isawaitable(maybe_output)
                else maybe_output
            )
            if isinstance(output, PatternResult):
                total_cost += output.cost
                outputs[step.name] = output.value
            else:
                outputs[step.name] = output
            await emit_trace(
                trace,
                TraceEvent.create("plan_step_end", {"step": step.name}),
            )

        return PlanResult(outputs=MappingProxyType(outputs), cost=total_cost)
