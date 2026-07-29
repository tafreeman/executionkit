# Evaluation

ExecutionKit's eval helpers run a function, check its result, and return
structured pass/fail data. They do not choose datasets, define product quality,
or make model results repeatable.

## Run repeatable cases

```python
from executionkit import EvalCase, MockProvider, consensus, run_eval_suite


async def run_case() -> str:
    provider = MockProvider(responses=["FR", "FR", "DE"])
    result = await consensus(
        provider,
        "Return only the ISO country code for France.",
        num_samples=3,
    )
    return result.value


def check_case(value: str) -> str | None:
    return None if value == "FR" else f"expected FR, got {value!r}"


report = await run_eval_suite(
    [EvalCase(name="country_code", run=run_case, check=check_case)]
)

print(report.summary())
assert report.passed
```

`run` and `check` may be sync or async. The check result is interpreted as:

| Return value | Outcome |
|---|---|
| `None`, `True`, or `""` | Pass |
| `False` | Fail with a generic reason |
| Non-empty string | Fail with that string as the reason |

An exception in `run` or `check` becomes a failed `EvalResult`. The remaining
cases still run.

For repeatable cases, use `MockProvider` or pure functions and require
`report.passed`.

## Use an accuracy threshold

Live model output can vary. Set `min_accuracy` only when a partial pass rate is
an intentional part of the eval definition:

```python
report = await run_eval_suite(cases, min_accuracy=0.8)

if not report.accuracy_passed:
    for failure in report.failures:
        print(failure.name, failure.reason)
```

`report.passed` still means every case passed. `report.accuracy_passed`
compares the measured accuracy with `min_accuracy`.

Do not lower a threshold merely to make an unstable run green. Record the
model, endpoint, prompt version, dataset version, and sample size outside the
basic `EvalReport` when those values matter.

## Evaluate conversation state

`ConversationScript` drives several text-only turns through one `Kit`:

```python
from executionkit import (
    ConversationScript,
    Kit,
    MockProvider,
    Turn,
    run_conversation_script,
)


def mentions_order(result) -> str | None:
    return None if "12345" in result.value else "order id missing"


script = ConversationScript(
    name="order_context",
    turns=(
        Turn("Remember order 12345.", mentions_order),
        Turn("Which order did I mention?", mentions_order),
    ),
)

kit = Kit(MockProvider(responses=["Order 12345 noted.", "You mentioned 12345."]))
report = await run_conversation_script(script, kit)
```

The helper calls `kit.turn()` without a tool list. Use a normal `EvalCase` when
the conversation must register tools or inspect application state around each
turn.

## Enable a live provider

```python
from executionkit import live_provider_from_env

provider = live_provider_from_env()
if provider is None:
    print("live eval disabled")
```

Set:

```text
EXECUTIONKIT_LIVE_EVAL=1
EXECUTIONKIT_BASE_URL=<OpenAI-compatible base URL>
EXECUTIONKIT_MODEL=<model ID>
EXECUTIONKIT_API_KEY=<optional key>
```

When the enable flag is absent, the helper returns `None`. When it is set,
missing base URL or model values raise `ValueError`.

Keep live checks separate from required repeatable checks. A live run can fail
because of endpoint availability, rate limits, model changes, or sampling
variation even when package behavior is unchanged.

## Repository eval tiers

The repository uses several tiers for different questions:

| Tier | Question | Required for normal CI |
|---|---|---|
| Unit and golden cases | Does package code return the expected values and metadata for fixed inputs? | Yes |
| Failure corpus | Does package code handle named malformed or hostile inputs as specified? | Yes |
| Live provider | Can the package run against a configured real endpoint, and what outputs does that endpoint produce? | No |
| Judge calibration | Does the chosen judge rank controlled good and bad answers in the expected order? | No |
| Claude corpus review | Does an external model agree with the written expected outcome for each failure case? | No |

Only the first two tiers are repeatable package gates. Live and judge tiers are
additional evidence; they are not proof of general model quality.

## Build useful cases

A good eval case states:

- the behavior being checked;
- the input and relevant configuration;
- the expected result or failure mode;
- why the check is stable; and
- which change should cause it to fail.

Avoid checks that only assert that a non-empty string was returned. Prefer
exact values, bounded invariants, metadata, error types, or application rules.

## Related

- [Evaluation API](../api/evaluation.md)
- [Conversational assistant recipe](../recipes/assistant.md)
- [ADR-006: failure corpus](../adr/006-eval-failure-corpus.md)
