"""React loop: tool-augmented reasoning.

Demonstrates Tool definitions, the think-act-observe cycle, and
tool_calls_made / rounds metadata. Uses a calculator tool and a
mock weather lookup tool — no external services required.

Run:
    OPENAI_API_KEY=sk-... python examples/react_tool_use.py
"""

import ast
import asyncio
import operator as _op
import os
from typing import Any

from executionkit import Provider, react_loop
from executionkit.types import Tool

_SAFE_OPS: dict[type, Any] = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.Pow: _op.pow,
    ast.USub: _op.neg,
}


def _safe_eval(expression: str) -> float:
    """Evaluate a math expression safely using AST (no eval/exec)."""

    def _eval(node: ast.expr) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsafe expression: {ast.dump(node)}")

    tree = ast.parse(expression, mode="eval")
    return _eval(tree.body)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


async def _calculator(expression: str) -> str:
    """Safely evaluate a numeric math expression."""
    try:
        result = _safe_eval(expression)
        return str(result)
    except Exception as exc:
        return f"Error: {exc}"


calculator_tool = Tool(
    name="calculator",
    description=(
        "Evaluate a mathematical expression and return the numeric result. "
        "Supports basic arithmetic (+, -, *, /), powers (**), and negation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": (
                    "A numeric arithmetic expression, e.g. '17 * 83' or '2 ** 10'"
                ),
            },
        },
        "required": ["expression"],
    },
    execute=_calculator,
    timeout=5.0,
)


# Mock weather database — no external API needed.
_WEATHER_DB: dict[str, dict[str, str]] = {
    "london": {"temp": "12°C", "condition": "Cloudy", "humidity": "78%"},
    "new york": {"temp": "18°C", "condition": "Sunny", "humidity": "55%"},
    "tokyo": {"temp": "22°C", "condition": "Partly cloudy", "humidity": "65%"},
    "sydney": {"temp": "25°C", "condition": "Clear", "humidity": "48%"},
}


async def _weather_lookup(city: str) -> str:
    """Return mock current weather for a city."""
    key = city.lower().strip()
    if key in _WEATHER_DB:
        data = _WEATHER_DB[key]
        return (
            f"{city.title()}: {data['condition']}, {data['temp']}, "
            f"humidity {data['humidity']}"
        )
    return f"Weather data not available for '{city}'."


weather_tool = Tool(
    name="get_weather",
    description="Get the current weather conditions for a city.",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "Name of the city, e.g. 'London' or 'New York'",
            },
        },
        "required": ["city"],
    },
    execute=_weather_lookup,
    timeout=5.0,
)


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


async def calculator_example(provider: Provider) -> None:
    print("--- Calculator tool ---")
    result = await react_loop(
        provider,
        "What is the square root of 1764, and then multiply that result by 17?",
        tools=[calculator_tool],
        max_rounds=6,
    )
    print(f"Answer: {result}")
    print(f"Rounds: {result.metadata['rounds']}")
    print(f"Tool calls: {result.metadata['tool_calls_made']}")
    print(f"Cost: {result.cost}")
    print()


async def weather_example(provider: Provider) -> None:
    print("--- Weather lookup tool ---")
    result = await react_loop(
        provider,
        "What is the weather like in London and Tokyo right now? Which city is warmer?",
        tools=[weather_tool],
        max_rounds=6,
    )
    print(f"Answer: {result}")
    print(f"Rounds: {result.metadata['rounds']}")
    print(f"Tool calls: {result.metadata['tool_calls_made']}")
    print(f"Cost: {result.cost}")
    print()


async def multi_tool_example(provider: Provider) -> None:
    print("--- Multiple tools together ---")
    result = await react_loop(
        provider,
        "The temperature in New York is 18°C and in Sydney is 25°C. "
        "What is the average temperature in Fahrenheit? "
        "(Use the calculator. Formula: F = C * 9/5 + 32)",
        tools=[calculator_tool, weather_tool],
        max_rounds=8,
    )
    print(f"Answer: {result}")
    print(f"Rounds: {result.metadata['rounds']}")
    print(f"Tool calls: {result.metadata['tool_calls_made']}")
    print(f"Cost: {result.cost}")
    print()


async def main() -> None:
    provider = Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    )

    await calculator_example(provider)
    await weather_example(provider)
    await multi_tool_example(provider)


if __name__ == "__main__":
    asyncio.run(main())
