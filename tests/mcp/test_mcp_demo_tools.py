"""Tests for the fixed, side-effect-free demo tools used by the react_loop tool.

These exercise the restricted-AST calculator (safe arithmetic, no code
execution) and the echo tool directly, since their branches are not all reached
via the dispatch-layer tests.
"""

from __future__ import annotations

from executionkit.mcp._demo_tools import (
    DEMO_TOOLS,
    calculator_tool,
    echo_tool,
)


class TestCalculatorTool:
    async def test_evaluates_basic_arithmetic(self) -> None:
        assert await calculator_tool.execute(expression="17 * 83") == "1411.0"

    async def test_supports_power_and_negation(self) -> None:
        assert await calculator_tool.execute(expression="2 ** 10") == "1024.0"
        assert await calculator_tool.execute(expression="-3 + 5") == "2.0"

    async def test_rejects_names_without_executing(self) -> None:
        # A bare name would be code execution in eval(); the AST walker rejects
        # it and returns a generic error string rather than raising or running.
        result = await calculator_tool.execute(expression="__import__('os')")
        assert result.startswith("Error")

    async def test_rejects_function_calls(self) -> None:
        result = await calculator_tool.execute(expression="print(1)")
        assert result.startswith("Error")

    async def test_rejects_syntactically_invalid_expression(self) -> None:
        result = await calculator_tool.execute(expression="1 +")
        assert result.startswith("Error")


class TestEchoTool:
    async def test_echoes_text_verbatim(self) -> None:
        assert await echo_tool.execute(text="hello world") == "hello world"


class TestDemoToolset:
    def test_toolset_contains_calculator_and_echo(self) -> None:
        names = {tool.name for tool in DEMO_TOOLS}
        assert names == {"calculator", "echo"}

    def test_tool_schemas_disallow_extra_properties(self) -> None:
        # additionalProperties: False keeps MCP-driven tool calls tightly scoped.
        for tool in DEMO_TOOLS:
            assert tool.parameters["additionalProperties"] is False
