# Workflows and approvals

ExecutionKit provides three small coordination helpers:

- `Router` selects a provider before one pattern call;
- `Workflow` runs named steps when their dependencies are complete; and
- `Plan` runs named steps in order.

They run in the current process. They do not provide a database, queue,
scheduler, worker pool, or distributed lock.

## Route a call

```python
from executionkit import RouteRule, Router, consensus

router = Router(
    rules=[
        RouteRule(
            name="review",
            provider=review_provider,
            predicate=lambda prompt, context: context.get("mode") == "review",
        ),
    ],
    fallback=default_provider,
)

result = await router.run(
    consensus,
    "Return only 'pass' or 'fail' for this check.",
    context={"mode": "review"},
    num_samples=3,
)
```

Routing `context` is visible only to predicates. Other keyword arguments go to
the pattern. Rules run in order; the first true predicate wins. If none match,
the fallback provider is used.

Predicates are caller code. Keep them fast and free of side effects.

## Run dependency-ordered steps

```python
from executionkit import Step, Workflow


async def load(context: dict[str, object]) -> list[str]:
    return ["alpha", "beta"]


async def summarize(context: dict[str, object]) -> str:
    items = context["load"]
    assert isinstance(items, list)
    return ", ".join(str(item) for item in items)


workflow = Workflow(
    [
        Step(name="load", run=load),
        Step(name="summarize", run=summarize, depends_on=("load",)),
    ]
)

result = await workflow.run({"request_id": "r-123"})
print(result.outputs["summarize"])
print(result.cost)
```

Each step receives a copy of the outputs available when its batch starts.
Steps that are ready in the same batch run concurrently. A step may return a
plain value or `PatternResult`; workflow cost includes only returned
`PatternResult.cost` values.

Step names must be unique, dependencies must name existing steps, and a key in
`initial_context` cannot match a step name.

### Save and resume

`Workflow` calls `checkpoint_fn` after each completed batch:

```python
import json
from pathlib import Path

from executionkit import WorkflowCheckpoint

checkpoint_path = Path("workflow-checkpoint.json")


def save(checkpoint: WorkflowCheckpoint) -> None:
    checkpoint_path.write_text(
        json.dumps(checkpoint.to_dict()),
        encoding="utf-8",
    )


result = await workflow.run(checkpoint_fn=save)
```

Resume with:

```python
saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
checkpoint = WorkflowCheckpoint.from_dict(saved)
result = await workflow.run(resume_from=checkpoint, checkpoint_fn=save)
```

The package does not write files itself; the example callback does. In an
application, write atomically and protect the checkpoint with the same access
controls as the workflow data.

Resume treats names present in `checkpoint.outputs` as completed steps.
`step_index` records progress but is not the source used to decide which steps
to skip. Step outputs must be JSON-compatible if you store them as JSON.

An exception from `checkpoint_fn` propagates and stops the workflow after the
batch has run. Make the callback idempotent if the application may retry it.

## Run an ordered plan

```python
from executionkit import Plan, PlanStep


def collect(context: dict[str, object]) -> list[str]:
    return ["one", "two"]


async def write(context: dict[str, object]) -> str:
    items = context["collect"]
    assert isinstance(items, list)
    return ", ".join(str(item) for item in items)


plan = Plan(
    [
        PlanStep("collect", "Collect source values", collect),
        PlanStep("write", "Join the source values", write),
    ]
)

result = await plan.execute()
```

Plan steps run one at a time in declaration order. The `instruction` field is
descriptive data supplied to approval callbacks; `Plan` does not interpret it
or send it to a model.

## Require approval

```python
from executionkit import ApprovalDecision, ApprovalGate


def decide(request) -> ApprovalDecision:
    approved = request.subject in {"load", "summarize"}
    return ApprovalDecision(approved=approved, reason="policy result")


gate = ApprovalGate(
    decide,
    timeout_seconds=30.0,
    on_timeout="deny",
)

result = await workflow.run(approval_gate=gate)
```

The callback may be sync or async. Sync callbacks run in a worker thread so a
timeout can still be enforced.

Timeout policies are:

| Policy | Result |
|---|---|
| `raise` | Raise `ApprovalTimeoutError`. This is the default. |
| `deny` | Return a denied decision. A required gate then raises `ApprovalDeniedError`. |
| `approve` | Approve after a timeout. This is fail-open and emits a warning. |

`Workflow` and `Plan` call `ApprovalGate.require()`, so denial stops execution.
`react_loop()` calls `request()` and turns denial into a tool observation so
the model can choose another action.

An approval gate is not authorization by itself. The application still needs
to authenticate the user and enforce permissions inside the protected
operation.

## Choose the right level

| Need | Use |
|---|---|
| Select one provider from request context | `Router` |
| Run a small dependency graph once | `Workflow` |
| Run a fixed sequence once | `Plan` |
| Persist across process restarts | `Workflow` plus caller-owned checkpoint storage |
| Schedule work across machines | A workflow runtime outside ExecutionKit |
| Coordinate several autonomous agents | A higher-level agent runtime |

## Related

- [Execution helper API](../api/execution.md)
- [Architecture](../architecture.md)
- [Security](../security.md)
