---
tags:
  - recipe
  - assistant
---

# Building a conversational assistant

A chat assistant needs three things ExecutionKit gives you out of the box:
stateful turns, tool use, and honest cost accounting. `Kit.turn()` threads the
running transcript through `react_loop` so the model can resolve references like
"when will it arrive?" against earlier turns — no manual message bookkeeping.

## The pattern

Seed a `Kit` with a system prompt, give it a `Tool`, then loop calling
`turn()`. Each turn appends the user message, runs the full think-act-observe
loop (executing tools as needed), and records the assistant reply in
`kit.messages`. Cumulative spend lands in `kit.usage`.

```python
import asyncio
import os
from executionkit import Kit, Provider, Tool

# A tiny in-memory backend stands in for a real order service.
_ORDERS: dict[str, dict[str, str]] = {
    "12345": {"item": "Mechanical keyboard", "status": "shipped", "eta": "Jun 21"},
    "67890": {"item": "USB-C cable", "status": "processing", "eta": "Jun 25"},
}

async def lookup_order(order_id: str) -> str:
    """Return the status and ETA for an order id."""
    order = _ORDERS.get(order_id.strip())
    if order is None:
        return f"No order found with id {order_id!r}."
    return (
        f"Order {order_id}: {order['item']} — status {order['status']}, "
        f"ETA {order['eta']}."
    )

order_tool = Tool(
    name="lookup_order",
    description="Look up the status and ETA of a customer order by its id.",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order id, e.g. '12345'.",
            },
        },
        "required": ["order_id"],
    },
    execute=lookup_order,
    timeout=5.0,
)

SYSTEM_PROMPT = (
    "You are a concise customer-support assistant. Use the lookup_order tool "
    "whenever the user asks about an order. Refer back to earlier turns so the "
    "user does not have to repeat the order id."
)


async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    ) as provider:
        # Seed the transcript with a system message; turn() carries it forward.
        kit = Kit(provider, messages=[{"role": "system", "content": SYSTEM_PROMPT}])

        conversation = (
            "Hi, can you check on order 12345?",
            "Thanks — when will it arrive?",   # "it" resolves via prior turns
            "And is order 67890 shipped yet?",
        )
        for user_text in conversation:
            print(f"User:      {user_text}")
            result = await kit.turn(user_text, tools=[order_tool])
            print(f"Assistant: {result.value}")

        # Inspect the running transcript and cumulative spend.
        print(f"\nTranscript length: {len(kit.messages)} messages")
        print(f"Total usage:       {kit.usage}")

asyncio.run(main())
```

### What `turn()` carries

- **`kit.messages`** is the full OpenAI-format transcript. `turn()` appends the
  user message, then replaces the list with the transcript returned by
  `react_loop` (the assistant turns, any tool-call/tool-result messages, and the
  final answer). The next `turn()` continues from there.
- **`result.value`** is the assistant's final text for that turn.
- **`result.metadata["tool_calls_made"]`** counts tool invocations this turn;
  **`result.metadata["messages"]`** is the same transcript now stored on `kit`.
- **`kit.usage`** is a `TokenUsage` (`input_tokens`, `output_tokens`,
  `llm_calls`) accumulated across every turn — even turns that raised, so the
  number never undercounts spend.
- A failed turn (e.g. budget exhausted) leaves `kit.messages` **unchanged**, so
  you can retry without a dangling user message.

!!! tip "The provider must support tools"
    `turn()` (like `react_loop`) requires a `ToolCallingProvider`. `Provider`
    and `MockProvider` both qualify. A provider without tool support raises
    `TypeError` before any call is made.

## Multi-turn intent + slots with `structured()`

For routing, analytics, or guardrails you often want a typed read of *what the
user wants* before — or instead of — generating a reply. `structured()` asks the
model for JSON, parses it, and repairs invalid output. Pass a `validator` to
reject responses that parse but don't match your contract.

```python
from typing import Any
from executionkit import Kit, structured


def validate_intent(value: dict[str, Any] | list[Any]) -> str | None:
    """Accept by returning None; reject with an error string for repair."""
    if not isinstance(value, dict):
        return "Expected a JSON object."
    if value.get("intent") not in {"order_status", "refund", "other"}:
        return "intent must be one of: order_status, refund, other."
    return None


async def classify_then_answer(kit: Kit, tools: list, user_text: str) -> str:
    intent = await structured(
        kit.provider,
        (
            "Extract the user's intent and any order id as JSON with keys "
            f"'intent' and 'order_id' (order_id may be null).\n\n{user_text}"
        ),
        validator=validate_intent,
    )
    slots = intent.value  # e.g. {"intent": "order_status", "order_id": "12345"}

    # Cheap guardrail: skip the tool-using turn for chit-chat.
    if slots["intent"] == "other":
        return "I can help with order status and refunds — what do you need?"

    result = await kit.turn(user_text, tools=tools)
    return result.value
```

`structured()` returns a `PatternResult` whose `value` is a `dict` or `list`.
Validation runs every attempt; a rejected value is fed back to the model with
the error message and one repair is attempted per `max_retries` (default 3).
Note the classifier call goes through `kit.provider` directly, so its cost is
**not** folded into `kit.usage` — only `turn()`/`react()` calls made *through*
the Kit are tracked. Add `kit._record(intent.cost)` only if you maintain the Kit
yourself; otherwise account for classifier spend separately.

## Streaming

Token-by-token output makes an assistant feel responsive. There is an important
honesty caveat in how ExecutionKit streams.

`Kit.stream_react_loop` streams **one** model generation and does **not**
execute tools — tool-call deltas carry no message content, so a streamed
generation that decides to call a tool would emit nothing useful and the tool
would never run. The same is true of `Kit.stream_consensus`, which streams a
single sample rather than voting.

The reliable pattern is therefore two-phase:

1. Run the full `turn()` (or `react_loop`) for any turn that may use tools.
   Surface progress through the `trace=` callback.
2. Stream **only the final answer turn** — a turn you know is pure text — with
   `stream_react_loop`.

```python
from executionkit import Kit, Provider, TraceEvent


async def on_trace(event: TraceEvent) -> None:
    # Tool progress surfaces here even though streaming can't carry it.
    if event.kind in {"tool_call_start", "tool_call_end"}:
        print(f"[{event.kind}] {dict(event.payload)}")


async def stream_demo(kit: Kit, tools: list) -> None:
    # Phase 1: tool-using turn runs fully; trace reports tool activity.
    await kit.turn("Check on order 12345.", tools=tools, trace=on_trace)

    # Phase 2: stream a final, text-only turn for a responsive feel.
    streamed = await kit.stream_react_loop("Summarize that in one sentence.")
    async for chunk in streamed.text_stream:
        print(chunk, end="", flush=True)
    print()
    # cost is accurate only after the stream is fully drained.
    print(f"streamed-turn usage: {streamed.cost}")
```

!!! warning "Do not expect tools while streaming"
    `tools=` is accepted by `stream_react_loop` for signature parity but is
    **never executed**. Reach for streaming only on the final, answer-only turn;
    use the non-streaming `turn()` for everything that touches a tool.

`stream_consensus` / `stream_react_loop` return a `StreamingPatternResult`.
Its `cost` is a live view — zero until you finish iterating `text_stream`, then
accurate. Draining the stream folds that spend into `kit.usage` like any other
Kit call.

## Evaluating the assistant

Multi-turn behavior is exactly the kind of thing that regresses silently. Drive
a fresh `Kit` through a scripted conversation and assert on each turn with the
built-in eval harness — `EvalCase`, `run_eval_suite`, and `EvalReport`. Use
`MockProvider` so the eval is deterministic and never touches the network.

```python
import asyncio
from executionkit import (
    EvalCase,
    Kit,
    LLMResponse,
    MockProvider,
    ToolCall,
    run_eval_suite,
)

# The mock plays a fixed script: round 1 calls the tool, round 2 answers from
# the tool result, then a follow-up answer that relies on prior context.
_SCRIPT = [
    LLMResponse(
        content="",
        tool_calls=(ToolCall(id="c1", name="lookup_order", arguments={"order_id": "12345"}),),
    ),
    "Order 12345 (Mechanical keyboard) is shipped, ETA Jun 21.",
    "It should arrive on Jun 21.",  # resolves "it" from the earlier turn
]


async def run_conversation() -> Kit:
    kit = Kit(
        MockProvider(responses=_SCRIPT),
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
    )
    await kit.turn("Check on order 12345.", tools=[order_tool])
    await kit.turn("When will it arrive?", tools=[order_tool])
    return kit


def check_eta_mentioned(kit: Kit) -> str | None:
    last = kit.messages[-1]
    return None if "Jun 21" in str(last.get("content", "")) else "ETA not carried across turns"


async def main() -> None:
    report = await run_eval_suite(
        [
            EvalCase(
                name="eta_resolves_across_turns",
                run=run_conversation,
                check=check_eta_mentioned,
            ),
        ]
    )
    print(report.summary())          # e.g. "1/1 passed (100.0% accuracy)"
    assert report.passed

asyncio.run(main())
```

`EvalCase.run` may be sync or async and may return anything — here it returns the
driven `Kit` so `check` can inspect `kit.messages`, `kit.usage`, or any turn's
result. `check` returns `None`/`True` to pass, or a reason string to fail.
`run_eval_suite` aggregates into an `EvalReport`: `report.passed` is `True` only
when every case passes, `report.accuracy` is the pass fraction, and
`report.summary()` gives a one-line readout. For live, non-deterministic suites
pass `min_accuracy=` and gate on `report.accuracy_passed` instead.

## Related

- [Provider Setup](../getting-started/providers.md) — configuring the provider a Kit wraps.
- [Combining patterns](composition.md) — pipe `structured` intent extraction into a generation step.
- [Cost-aware routing](cost-routing.md) — send cheap turns to a small model, hard ones to a strong one.
