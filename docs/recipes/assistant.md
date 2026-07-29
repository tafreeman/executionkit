---
tags:
  - recipe
  - tools
---

# Build a stateful tool-using assistant

`Kit.turn()` keeps an OpenAI-format message history between calls. Each turn
runs `react_loop`, executes requested tools, and stores the returned transcript
for the next turn.

```python
import asyncio
import json
import os

from executionkit import Kit, Provider, Tool


async def lookup_ticket(ticket_id: str) -> str:
    records = {
        "INC-1042": {"status": "resolved", "owner": "platform"},
        "INC-1077": {"status": "investigating", "owner": "payments"},
    }
    return json.dumps(records.get(ticket_id, {"status": "not_found"}))


ticket_tool = Tool(
    name="lookup_ticket",
    description="Return the current status and owner of an incident ticket.",
    parameters={
        "type": "object",
        "properties": {
            "ticket_id": {
                "type": "string",
                "description": "Incident identifier such as INC-1042.",
            }
        },
        "required": ["ticket_id"],
        "additionalProperties": False,
    },
    execute=lookup_ticket,
    timeout=5.0,
)


async def main() -> None:
    provider = Provider(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ["LLM_MODEL"],
    )

    async with Kit(provider) as kit:
        first = await kit.turn(
            "What is the status of INC-1042?",
            tools=[ticket_tool],
            max_rounds=4,
            max_tool_calls_per_round=2,
        )
        print(first.value)

        second = await kit.turn(
            "Which team owns it?",
            tools=[ticket_tool],
            max_rounds=4,
            max_tool_calls_per_round=2,
        )
        print(second.value)
        print(kit.usage)


asyncio.run(main())
```

The concrete `Provider` uses the OpenAI tool-calling wire format and reports
tool support. A custom provider must satisfy `ToolCallingProvider` before
`Kit.turn()` or `react_loop()` will accept it.

## State and accounting

- `kit.messages` is the current conversation transcript.
- A successful turn replaces the transcript with the messages returned by
  `react_loop`.
- A failed turn leaves the previous transcript unchanged.
- `kit.usage` accumulates calls made through the Kit, including partial cost
  attached to an `ExecutionKitError`.
- Calls made directly through `kit.provider` are not recorded by the Kit.

Persist `kit.messages` in the application if a conversation must survive a
process restart. Treat the transcript as sensitive data: it can contain user
input, model output, tool arguments, and tool results.

## Tool boundary

Tool schema validation is an input check, not an authorization system. A tool
should still validate identifiers, enforce the caller's permissions, limit
side effects, and return only the data needed for the answer. Use
`ApprovalGate` before high-impact operations.

Tools requested in the same round run concurrently. Do not assume one tool
call sees another call's side effects. Set a bounded timeout on every external
operation.

## Test the conversation

Use `ConversationScript` for fixed, tool-free turn scripts. For a tool-using
conversation, create an `EvalCase` that builds a `Kit`, runs the required turns,
and asserts the final value or metadata. Tests should use `MockProvider`; live
provider tests should remain explicit and opt-in.

See [ReAct loop](../patterns/react-loop.md) for the execution limits and
[Evaluation](../guides/evaluation.md) for test examples.
