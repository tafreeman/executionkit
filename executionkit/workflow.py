"""Lightweight dependency workflow execution."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from executionkit.approval import ApprovalGate, ApprovalRequest
from executionkit.errors import ExecutionKitError
from executionkit.observability import TraceCallback, TraceEvent, emit_trace
from executionkit.types import PatternResult, TokenUsage

WorkflowRun: TypeAlias = Callable[[dict[str, Any]], Awaitable[Any] | Any]


@dataclass(frozen=True, slots=True)
class Step:
    """A named workflow step with optional dependencies."""

    name: str
    run: WorkflowRun
    depends_on: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Outputs and aggregate cost from a workflow run."""

    outputs: MappingProxyType[str, Any]
    cost: TokenUsage = field(default_factory=TokenUsage)


class Workflow:
    """Run named steps once their dependencies are available."""

    def __init__(self, steps: Sequence[Step]) -> None:
        self.steps = tuple(steps)
        self._validate()

    def _validate(self) -> None:
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("Workflow step names must be unique")
        known = set(names)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(
                    f"Workflow step {step.name!r} has unknown dependencies: "
                    f"{sorted(missing)}"
                )

    async def _run_step(
        self,
        step: Step,
        context: dict[str, Any],
        *,
        trace: TraceCallback | None,
        approval_gate: ApprovalGate | None,
    ) -> Any:
        if approval_gate is not None:
            await approval_gate.require(
                ApprovalRequest.create(
                    "workflow_step",
                    step.name,
                    {"depends_on": step.depends_on, **dict(step.metadata)},
                )
            )
        await emit_trace(
            trace,
            TraceEvent.create("workflow_step_start", {"step": step.name}),
        )
        maybe_output = step.run(dict(context))
        output = (
            await maybe_output if inspect.isawaitable(maybe_output) else maybe_output
        )
        await emit_trace(
            trace,
            TraceEvent.create("workflow_step_end", {"step": step.name}),
        )
        return output

    async def run(
        self,
        initial_context: Mapping[str, Any] | None = None,
        *,
        trace: TraceCallback | None = None,
        approval_gate: ApprovalGate | None = None,
    ) -> WorkflowResult:
        outputs: dict[str, Any] = dict(initial_context or {})
        pending = {step.name: step for step in self.steps}
        total_cost = TokenUsage()

        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dep in outputs for dep in step.depends_on)
            ]
            if not ready:
                raise ExecutionKitError("Workflow dependencies could not be resolved")

            results = await asyncio.gather(
                *[
                    self._run_step(
                        step,
                        outputs,
                        trace=trace,
                        approval_gate=approval_gate,
                    )
                    for step in ready
                ]
            )
            for step, output in zip(ready, results, strict=True):
                if isinstance(output, PatternResult):
                    total_cost += output.cost
                    outputs[step.name] = output.value
                else:
                    outputs[step.name] = output
                pending.pop(step.name)

        return WorkflowResult(outputs=MappingProxyType(outputs), cost=total_cost)
