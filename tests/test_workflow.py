"""Tests for WorkflowCheckpoint persist/resume support in Workflow.run()."""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any

from executionkit.types import PatternResult, TokenUsage
from executionkit.workflow import Step, Workflow, WorkflowCheckpoint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step_fn(label: str) -> Any:
    """Return a sync step function that returns *label*."""

    def _run(ctx: dict[str, Any]) -> str:
        return label

    return _run


def _make_steps(n: int) -> list[Step]:
    """Return ``n`` sequential steps (step_1 → step_2 → … → step_n)."""
    steps: list[Step] = []
    for i in range(1, n + 1):
        name = f"step_{i}"
        depends_on: tuple[str, ...] = (f"step_{i - 1}",) if i > 1 else ()
        steps.append(
            Step(name=name, run=_step_fn(f"result_{i}"), depends_on=depends_on)
        )
    return steps


def _checkpoint(
    step_index: int,
    outputs: dict[str, Any],
    cost: TokenUsage | None = None,
) -> WorkflowCheckpoint:
    """Convenience constructor that wraps outputs in MappingProxyType."""
    return WorkflowCheckpoint(
        step_index=step_index,
        outputs=MappingProxyType(outputs),
        cost=cost if cost is not None else TokenUsage(),
    )


# ---------------------------------------------------------------------------
# Checkpoint emission
# ---------------------------------------------------------------------------


async def test_checkpoint_fn_called_after_each_batch() -> None:
    """checkpoint_fn must be invoked once per completed batch of steps."""
    checkpoints: list[WorkflowCheckpoint] = []

    steps = _make_steps(3)
    workflow = Workflow(steps)
    await workflow.run(checkpoint_fn=checkpoints.append)

    # Linear chain → 3 batches of 1 step each
    assert len(checkpoints) == 3


async def test_checkpoint_step_index_increments() -> None:
    """step_index in each checkpoint reflects cumulative completed-step count."""
    checkpoints: list[WorkflowCheckpoint] = []

    steps = _make_steps(4)
    workflow = Workflow(steps)
    await workflow.run(checkpoint_fn=checkpoints.append)

    assert [cp.step_index for cp in checkpoints] == [1, 2, 3, 4]


async def test_checkpoint_outputs_accumulate() -> None:
    """Each checkpoint carries all outputs completed up to that point."""
    checkpoints: list[WorkflowCheckpoint] = []

    steps = _make_steps(3)
    workflow = Workflow(steps)
    await workflow.run(checkpoint_fn=checkpoints.append)

    assert set(checkpoints[0].outputs.keys()) == {"step_1"}
    assert set(checkpoints[1].outputs.keys()) == {"step_1", "step_2"}
    assert set(checkpoints[2].outputs.keys()) == {"step_1", "step_2", "step_3"}


async def test_checkpoint_cost_accumulates() -> None:
    """Checkpoint cost must equal the sum of all PatternResult costs so far."""
    checkpoints: list[WorkflowCheckpoint] = []
    call_count = 0

    async def costly_step(ctx: dict[str, Any]) -> PatternResult[str]:
        nonlocal call_count
        call_count += 1
        return PatternResult(f"v{call_count}", cost=TokenUsage(llm_calls=1))

    workflow = Workflow(
        [
            Step("a", costly_step),
            Step("b", costly_step, depends_on=("a",)),
            Step("c", costly_step, depends_on=("b",)),
        ]
    )
    await workflow.run(checkpoint_fn=checkpoints.append)

    assert [cp.cost.llm_calls for cp in checkpoints] == [1, 2, 3]


async def test_checkpoint_fn_not_called_without_argument() -> None:
    """Default behavior (no checkpoint_fn) must produce no side effects."""
    called: list[object] = []

    steps = _make_steps(2)
    workflow = Workflow(steps)
    result = await workflow.run()  # no checkpoint_fn

    assert called == []
    assert "step_1" in result.outputs
    assert "step_2" in result.outputs


# ---------------------------------------------------------------------------
# Resume from checkpoint
# ---------------------------------------------------------------------------


async def test_resume_skips_completed_steps() -> None:
    """When resume_from is provided, steps already in its outputs are not re-run."""
    executed: list[str] = []

    async def tracked(name: str) -> Any:
        async def _run(ctx: dict[str, Any]) -> str:
            executed.append(name)
            return name

        return _run

    step_a_fn = await tracked("a")
    step_b_fn = await tracked("b")
    step_c_fn = await tracked("c")

    workflow = Workflow(
        [
            Step("a", step_a_fn),
            Step("b", step_b_fn, depends_on=("a",)),
            Step("c", step_c_fn, depends_on=("b",)),
        ]
    )

    # Simulate "a" and "b" already done
    checkpoint = _checkpoint(step_index=2, outputs={"a": "a", "b": "b"})
    executed.clear()

    result = await workflow.run(resume_from=checkpoint)

    assert "c" in executed
    assert "a" not in executed
    assert "b" not in executed
    assert result.outputs["c"] == "c"


async def test_resume_restores_outputs_and_cost() -> None:
    """Resumed run must include prior outputs and accumulated cost in the result."""

    async def step_c(ctx: dict[str, Any]) -> PatternResult[str]:
        return PatternResult("c", cost=TokenUsage(llm_calls=2))

    workflow = Workflow(
        [
            Step("a", lambda ctx: "a"),
            Step("b", lambda ctx: "b", depends_on=("a",)),
            Step("c", step_c, depends_on=("b",)),
        ]
    )

    checkpoint = _checkpoint(
        step_index=2,
        outputs={"a": "prior_a", "b": "prior_b"},
        cost=TokenUsage(llm_calls=5),
    )

    result = await workflow.run(resume_from=checkpoint)

    assert result.outputs["a"] == "prior_a"
    assert result.outputs["b"] == "prior_b"
    assert result.outputs["c"] == "c"
    # 5 pre-existing + 2 from step_c
    assert result.cost.llm_calls == 7


async def test_resume_from_full_checkpoint_is_noop() -> None:
    """Resuming from a checkpoint where all steps are done returns immediately."""
    executed: list[str] = []

    async def side_effect(ctx: dict[str, Any]) -> str:
        executed.append("ran")
        return "x"

    workflow = Workflow(
        [Step("a", side_effect), Step("b", side_effect, depends_on=("a",))]
    )

    full_checkpoint = _checkpoint(
        step_index=2,
        outputs={"a": "cached_a", "b": "cached_b"},
        cost=TokenUsage(llm_calls=3),
    )

    result = await workflow.run(resume_from=full_checkpoint)

    assert executed == []
    assert result.outputs["a"] == "cached_a"
    assert result.outputs["b"] == "cached_b"
    assert result.cost.llm_calls == 3


async def test_resume_produces_same_final_result_as_fresh_run() -> None:
    """A run resumed from mid-point must produce the same final outputs as a
    fresh run (deterministic steps)."""
    steps = _make_steps(5)
    workflow = Workflow(steps)

    # Full fresh run
    full_result = await workflow.run()

    # Collect checkpoint after step 3
    checkpoints: list[WorkflowCheckpoint] = []
    workflow2 = Workflow(_make_steps(5))
    await workflow2.run(checkpoint_fn=checkpoints.append)
    mid_checkpoint = checkpoints[2]  # after step_3

    # Resume from mid-point
    workflow3 = Workflow(_make_steps(5))
    resumed_result = await workflow3.run(resume_from=mid_checkpoint)

    assert dict(resumed_result.outputs) == dict(full_result.outputs)


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_checkpoint_to_dict_contains_plain_types() -> None:
    """to_dict must return only plain Python types (JSON-encodable)."""
    cp = _checkpoint(
        step_index=3,
        outputs={"step_1": "r1", "step_2": "r2"},
        cost=TokenUsage(input_tokens=10, output_tokens=5, llm_calls=2),
    )
    d = cp.to_dict()
    # Must not raise
    encoded = json.dumps(d)
    assert encoded  # non-empty


def test_checkpoint_json_round_trip() -> None:
    """from_dict(to_dict(cp)) must produce an equivalent WorkflowCheckpoint."""
    original = _checkpoint(
        step_index=7,
        outputs={"a": "alpha", "b": "beta"},
        cost=TokenUsage(input_tokens=100, output_tokens=50, llm_calls=4),
    )

    serialised = json.dumps(original.to_dict())
    restored = WorkflowCheckpoint.from_dict(json.loads(serialised))

    assert restored.step_index == original.step_index
    assert dict(restored.outputs) == dict(original.outputs)
    assert restored.cost == original.cost


def test_checkpoint_from_dict_restores_token_usage() -> None:
    """Individual TokenUsage fields must survive a dict round-trip."""
    data = {
        "step_index": 2,
        "outputs": {"x": 42},
        "cost": {"input_tokens": 11, "output_tokens": 22, "llm_calls": 3},
    }
    cp = WorkflowCheckpoint.from_dict(data)

    assert cp.cost.input_tokens == 11
    assert cp.cost.output_tokens == 22
    assert cp.cost.llm_calls == 3


# ---------------------------------------------------------------------------
# Default-behavior unchanged
# ---------------------------------------------------------------------------


async def test_no_checkpoint_no_resume_behavior_unchanged() -> None:
    """Without checkpoint_fn or resume_from, workflow behaves identically to
    the pre-checkpoint implementation."""

    async def root(ctx: dict[str, Any]) -> PatternResult[str]:
        return PatternResult("root", cost=TokenUsage(llm_calls=1))

    async def branch_a(ctx: dict[str, Any]) -> str:
        return f"{ctx['root']}:a"

    async def branch_b(ctx: dict[str, Any]) -> str:
        return f"{ctx['root']}:b"

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


async def test_checkpoint_fn_receives_immutable_outputs() -> None:
    """Outputs snapshot in each WorkflowCheckpoint must be a MappingProxyType."""
    checkpoints: list[WorkflowCheckpoint] = []
    workflow = Workflow(_make_steps(2))
    await workflow.run(checkpoint_fn=checkpoints.append)

    for cp in checkpoints:
        assert isinstance(cp.outputs, MappingProxyType)


# ---------------------------------------------------------------------------
# Finding #2 — async checkpoint_fn is actually awaited
# ---------------------------------------------------------------------------


async def test_async_checkpoint_fn_is_awaited() -> None:
    """An async checkpoint_fn must be awaited, not silently dropped."""
    recorded: list[int] = []

    async def async_checkpoint(cp: WorkflowCheckpoint) -> None:
        recorded.append(cp.step_index)

    workflow = Workflow(_make_steps(3))
    await workflow.run(checkpoint_fn=async_checkpoint)

    # Three sequential steps → three checkpoints, each with the correct index
    assert recorded == [1, 2, 3]


async def test_async_checkpoint_fn_receives_correct_outputs() -> None:
    """Async checkpoint_fn must receive the accumulated outputs at each batch."""
    snapshots: list[dict[str, Any]] = []

    async def async_checkpoint(cp: WorkflowCheckpoint) -> None:
        snapshots.append(dict(cp.outputs))

    workflow = Workflow(_make_steps(2))
    await workflow.run(checkpoint_fn=async_checkpoint)

    assert "step_1" in snapshots[0]
    assert "step_1" in snapshots[1]
    assert "step_2" in snapshots[1]


# ---------------------------------------------------------------------------
# Finding #3 — from_dict raises clear ValueError for missing/malformed keys
# ---------------------------------------------------------------------------


def test_from_dict_raises_for_missing_cost() -> None:
    """from_dict must raise ValueError (not KeyError) when 'cost' is absent."""
    data = {
        "step_index": 1,
        "outputs": {"step_1": "result_1"},
        # 'cost' deliberately omitted
    }
    try:
        WorkflowCheckpoint.from_dict(data)
    except ValueError as exc:
        assert "cost" in str(exc)
    else:
        raise AssertionError("Expected ValueError was not raised")


def test_from_dict_raises_for_missing_input_tokens() -> None:
    """from_dict must raise ValueError when 'input_tokens' is absent from cost."""
    data = {
        "step_index": 1,
        "outputs": {"step_1": "result_1"},
        "cost": {"output_tokens": 5, "llm_calls": 1},  # 'input_tokens' missing
    }
    try:
        WorkflowCheckpoint.from_dict(data)
    except ValueError as exc:
        assert "input_tokens" in str(exc)
    else:
        raise AssertionError("Expected ValueError was not raised")


def test_from_dict_raises_for_missing_step_index() -> None:
    """from_dict must raise ValueError when 'step_index' is absent."""
    data = {
        "outputs": {"step_1": "result_1"},
        "cost": {"input_tokens": 1, "output_tokens": 5, "llm_calls": 1},
        # 'step_index' deliberately omitted
    }
    try:
        WorkflowCheckpoint.from_dict(data)
    except ValueError as exc:
        assert "step_index" in str(exc)
    else:
        raise AssertionError("Expected ValueError was not raised")


def test_from_dict_raises_for_missing_outputs() -> None:
    """from_dict must raise ValueError when 'outputs' is absent."""
    data = {
        "step_index": 1,
        "cost": {"input_tokens": 1, "output_tokens": 5, "llm_calls": 1},
        # 'outputs' deliberately omitted
    }
    try:
        WorkflowCheckpoint.from_dict(data)
    except ValueError as exc:
        assert "outputs" in str(exc)
    else:
        raise AssertionError("Expected ValueError was not raised")


def test_from_dict_does_not_raise_keyerror_for_bad_input() -> None:
    """Corrupt checkpoint dicts must never surface a bare KeyError."""
    bad_inputs = [
        {},
        {"step_index": 1},
        {"step_index": 1, "outputs": {}, "cost": {}},
    ]
    for bad in bad_inputs:
        try:
            WorkflowCheckpoint.from_dict(bad)
        except ValueError:
            pass  # expected
        except KeyError as exc:  # pragma: no cover
            raise AssertionError(
                f"Bare KeyError raised instead of ValueError: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Finding #1 — gather_strict: parallel steps produce correct ordered outputs
# ---------------------------------------------------------------------------


async def test_parallel_steps_correct_outputs_after_gather_strict() -> None:
    """Parallel-ready steps (same dependency tier) must all produce correct
    results after the asyncio.gather → gather_strict swap."""
    execution_order: list[str] = []

    async def make_parallel_step(name: str) -> Any:
        async def _run(ctx: dict[str, Any]) -> str:
            execution_order.append(name)
            return f"output_{name}"

        return _run

    step_root_fn = await make_parallel_step("root")
    step_a_fn = await make_parallel_step("a")
    step_b_fn = await make_parallel_step("b")
    step_c_fn = await make_parallel_step("c")

    # 'a', 'b', and 'c' all depend on 'root' and are thus ready in one batch.
    workflow = Workflow(
        [
            Step("root", step_root_fn),
            Step("a", step_a_fn, depends_on=("root",)),
            Step("b", step_b_fn, depends_on=("root",)),
            Step("c", step_c_fn, depends_on=("root",)),
        ]
    )

    result = await workflow.run()

    assert result.outputs["root"] == "output_root"
    assert result.outputs["a"] == "output_a"
    assert result.outputs["b"] == "output_b"
    assert result.outputs["c"] == "output_c"
    # All four steps must have actually run
    assert set(execution_order) == {"root", "a", "b", "c"}


async def test_parallel_steps_ordering_matches_step_definition() -> None:
    """Results must map back to each step by name regardless of completion
    order (ordering guarantee from gather_strict's index-based assignment)."""
    import asyncio as _asyncio

    async def slow_step(ctx: dict[str, Any]) -> str:
        await _asyncio.sleep(0)  # yield to allow interleaving
        return "slow"

    async def fast_step(ctx: dict[str, Any]) -> str:
        return "fast"

    # Both 'slow' and 'fast' depend only on 'root' → run in same parallel batch.
    workflow = Workflow(
        [
            Step("root", lambda ctx: "root"),
            Step("slow", slow_step, depends_on=("root",)),
            Step("fast", fast_step, depends_on=("root",)),
        ]
    )

    result = await workflow.run()

    assert result.outputs["slow"] == "slow"
    assert result.outputs["fast"] == "fast"


# ---------------------------------------------------------------------------
# Finding EK#1 — initial_context key colliding with a step name must not
# silently skip the step. `outputs` membership used to double as both
# "seeded by initial_context" and "already executed"; a step whose name
# matched an initial_context key never ran, and the caller's seed was
# returned as its "output" with no error or warning.
# ---------------------------------------------------------------------------


async def test_initial_context_collision_with_step_name_raises_value_error() -> None:
    """A fresh run must raise ValueError, never silently return the seed.

    This is the exact runtime repro from the audit finding: a single-step
    workflow named "summary" seeded with initial_context={"summary": ...}
    must not return the seed as the step's output without running it.
    """
    executed: list[str] = []

    async def summarize(ctx: dict[str, Any]) -> str:
        executed.append("ran")
        return "real summary"

    workflow = Workflow([Step(name="summary", run=summarize)])

    try:
        await workflow.run(initial_context={"summary": "placeholder"})
    except ValueError as exc:
        assert "summary" in str(exc)
    else:
        raise AssertionError("Expected ValueError was not raised")

    # The step must never have run, and no partial state should leak out —
    # the collision is rejected up front, before any step is dispatched.
    assert executed == []


async def test_initial_context_collision_error_names_the_colliding_key() -> None:
    """The ValueError message must name the exact colliding key(s)."""
    workflow = Workflow([Step(name="report", run=lambda ctx: "x")])

    try:
        await workflow.run(initial_context={"report": "seed", "other": "kept"})
    except ValueError as exc:
        message = str(exc)
        assert "report" in message
        assert "other" not in message  # only the colliding key is named
    else:
        raise AssertionError("Expected ValueError was not raised")


async def test_initial_context_collision_lists_all_colliding_keys() -> None:
    """Multiple colliding keys are all named in the single raised error."""
    workflow = Workflow(
        [
            Step(name="alpha", run=lambda ctx: "alpha-real"),
            Step(name="beta", run=lambda ctx: "beta-real"),
        ]
    )

    try:
        await workflow.run(initial_context={"alpha": "seed-a", "beta": "seed-b"})
    except ValueError as exc:
        message = str(exc)
        assert "alpha" in message
        assert "beta" in message
    else:
        raise AssertionError("Expected ValueError was not raised")


async def test_initial_context_non_colliding_keys_still_seed_dependents() -> None:
    """A non-colliding initial_context key must still be readable by steps
    that depend on it — the fix must not break legitimate seeding."""

    async def greet(ctx: dict[str, Any]) -> str:
        return f"hello, {ctx['user_name']}"

    workflow = Workflow([Step(name="greeting", run=greet, depends_on=())])

    result = await workflow.run(initial_context={"user_name": "Ada"})

    assert result.outputs["greeting"] == "hello, Ada"


async def test_initial_context_none_does_not_raise() -> None:
    """No initial_context at all must never trigger the collision check."""
    executed: list[str] = []

    async def step_fn(ctx: dict[str, Any]) -> str:
        executed.append("ran")
        return "value"

    workflow = Workflow([Step(name="only", run=step_fn)])
    result = await workflow.run()

    assert executed == ["ran"]
    assert result.outputs["only"] == "value"


async def test_resume_from_checkpoint_unaffected_by_collision_check() -> None:
    """resume_from's own outputs may legitimately share step names — that is
    the intended "already executed" signal and must not raise."""

    async def step_c(ctx: dict[str, Any]) -> str:
        return "c-ran"

    workflow = Workflow(
        [
            Step("a", lambda ctx: "a"),
            Step("b", lambda ctx: "b", depends_on=("a",)),
            Step("c", step_c, depends_on=("b",)),
        ]
    )

    checkpoint = _checkpoint(step_index=2, outputs={"a": "prior_a", "b": "prior_b"})

    # Must not raise — resume_from is not initial_context.
    result = await workflow.run(resume_from=checkpoint)

    assert result.outputs["c"] == "c-ran"
