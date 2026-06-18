"""Lightweight dependency workflow execution."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from executionkit.approval import ApprovalGate, ApprovalRequest
from executionkit.engine.parallel import gather_strict
from executionkit.errors import ExecutionKitError
from executionkit.observability import TraceCallback, TraceEvent, emit_trace
from executionkit.types import PatternResult, TokenUsage

WorkflowRun: TypeAlias = Callable[[dict[str, Any]], Awaitable[Any] | Any]
CheckpointFn: TypeAlias = Callable[["WorkflowCheckpoint"], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class Step:
    """A named workflow step with optional dependencies."""

    name: str
    run: WorkflowRun
    depends_on: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    """Snapshot of workflow state after a completed step batch.

    Captures the step index (number of completed steps), accumulated
    outputs, and token budget consumed so far.  Both ``to_dict`` and
    ``from_dict`` use only plain Python types so the caller can serialise
    with any backend (JSON, pickle, database, etc.) without a dependency
    on this module.
    """

    step_index: int
    """Number of steps that have been completed."""

    outputs: MappingProxyType[str, Any]
    """Accumulated step outputs, keyed by step name."""

    cost: TokenUsage
    """Aggregate token usage consumed up to this checkpoint."""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain-Python dict.

        JSON-serializability depends on the caller ensuring that all step
        outputs stored in this checkpoint are themselves JSON-safe primitives.
        Non-primitive output values (e.g. custom objects, bytes) will cause
        ``json.dumps`` to raise when applied to the returned dict.
        """
        return {
            "step_index": self.step_index,
            "outputs": dict(self.outputs),
            "cost": {
                "input_tokens": self.cost.input_tokens,
                "output_tokens": self.cost.output_tokens,
                "llm_calls": self.cost.llm_calls,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowCheckpoint:
        """Restore a :class:`WorkflowCheckpoint` from a plain-Python dict.

        Raises
        ------
        ValueError
            If the dict is missing a required key or contains a value of the
            wrong type.  The message names the exact missing or malformed field
            so that callers can produce actionable diagnostics.
        """
        required_top: tuple[str, ...] = ("step_index", "outputs", "cost")
        required_cost: tuple[str, ...] = ("input_tokens", "output_tokens", "llm_calls")

        for key in required_top:
            if key not in data:
                raise ValueError(
                    f"WorkflowCheckpoint.from_dict: missing required key {key!r}"
                )

        if not isinstance(data["cost"], dict):
            raise ValueError(
                "WorkflowCheckpoint.from_dict: 'cost' must be a dict, "
                f"got {type(data['cost']).__name__!r}"
            )
        cost_data: dict[str, Any] = data["cost"]

        for key in required_cost:
            if key not in cost_data:
                raise ValueError(
                    f"WorkflowCheckpoint.from_dict: missing required key 'cost.{key}'"
                )

        if not isinstance(data["outputs"], dict):
            raise ValueError(
                "WorkflowCheckpoint.from_dict: 'outputs' must be a dict, "
                f"got {type(data['outputs']).__name__!r}"
            )

        return cls(
            step_index=int(data["step_index"]),
            outputs=MappingProxyType(dict(data["outputs"])),
            cost=TokenUsage(
                input_tokens=int(cost_data["input_tokens"]),
                output_tokens=int(cost_data["output_tokens"]),
                llm_calls=int(cost_data["llm_calls"]),
            ),
        )


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
        checkpoint_fn: CheckpointFn | None = None,
        resume_from: WorkflowCheckpoint | None = None,
    ) -> WorkflowResult:
        """Execute the workflow, optionally checkpointing after each batch.

        Parameters
        ----------
        initial_context:
            Key/value pairs injected into the step context before execution.
        trace:
            Optional async or sync callback receiving
            :class:`~executionkit.observability.TraceEvent` objects.
        approval_gate:
            Optional gate consulted before each step runs.
        checkpoint_fn:
            Called with a :class:`WorkflowCheckpoint` after each batch of
            completed steps.  The caller is responsible for persisting the
            checkpoint; this library imposes no storage requirement.
        resume_from:
            A previously saved :class:`WorkflowCheckpoint`.  Steps whose
            names already appear in ``resume_from.outputs`` are skipped;
            accumulated outputs and token budget are restored verbatim.
            When ``None`` (default), the workflow starts from the beginning.
        """
        # ------------------------------------------------------------------
        # Restore state from checkpoint (if any)
        # ------------------------------------------------------------------
        if resume_from is not None:
            outputs: dict[str, Any] = dict(resume_from.outputs)
            total_cost = resume_from.cost
        else:
            outputs = dict(initial_context or {})
            total_cost = TokenUsage()

        # Steps whose name already exists in outputs are already done.
        pending = {step.name: step for step in self.steps if step.name not in outputs}
        completed_count = len(self.steps) - len(pending)

        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dep in outputs for dep in step.depends_on)
            ]
            if not ready:
                raise ExecutionKitError("Workflow dependencies could not be resolved")

            results = await gather_strict(
                [
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

            completed_count += len(ready)

            if checkpoint_fn is not None:
                maybe_checkpoint = checkpoint_fn(
                    WorkflowCheckpoint(
                        step_index=completed_count,
                        outputs=MappingProxyType(dict(outputs)),
                        cost=total_cost,
                    )
                )
                if inspect.isawaitable(maybe_checkpoint):
                    await maybe_checkpoint

        return WorkflowResult(outputs=MappingProxyType(outputs), cost=total_cost)
