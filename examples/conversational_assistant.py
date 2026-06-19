"""Conversational assistant: multi-turn tool use with Kit.turn().

Demonstrates carrying conversation state across user turns. ``Kit.turn()``
threads the running transcript through ``react_loop`` and records each turn's
assistant reply in ``kit.messages``, so the model can resolve references like
"when will it arrive?" against earlier turns without the user repeating the
order id.

A tiny in-memory order-lookup tool stands in for a real backend — no external
services required beyond the LLM endpoint.

Run:
    OPENAI_API_KEY=sk-... python examples/conversational_assistant.py
"""

import asyncio
import os

from executionkit import Kit, Provider, Tool

# Mock order database — no external API needed.
_ORDERS: dict[str, dict[str, str]] = {
    "12345": {"item": "Mechanical keyboard", "status": "shipped", "eta": "Jun 21"},
    "67890": {"item": "USB-C cable", "status": "processing", "eta": "Jun 25"},
}


async def _lookup_order(order_id: str) -> str:
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
    execute=_lookup_order,
    timeout=5.0,
)

_SYSTEM_PROMPT = (
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
        # Seed the conversation with a system prompt; Kit.turn() appends each
        # user turn and the assistant's reply to kit.messages automatically.
        kit = Kit(provider, messages=[{"role": "system", "content": _SYSTEM_PROMPT}])

        conversation = (
            "Hi, can you check on order 12345?",
            "Thanks — when will it arrive?",  # "it" resolves via prior turns
            "And is order 67890 shipped yet?",
        )
        for user_text in conversation:
            print(f"User:      {user_text}")
            result = await kit.turn(user_text, tools=[order_tool])
            print(f"Assistant: {result.value}")
            print(
                f"           (tool calls: {result.metadata['tool_calls_made']}, "
                f"transcript length: {len(kit.messages)})\n"
            )

        print(f"Total cost: {kit.usage}")


if __name__ == "__main__":
    asyncio.run(main())
