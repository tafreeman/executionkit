"""Fixed, side-effect-free demo tools for the ``react_loop`` MCP tool.

Security boundary (ADR-012): MCP callers must **never** be able to register
arbitrary Python callables as tools. LLM output is untrusted (see the repo
security policy), and the tool bodies here run locally in the server process.
So the ``react_loop`` MCP tool exposes only this fixed, hard-coded toolset —
a calculator that evaluates arithmetic via a restricted AST walk (no
``eval``/``exec``) and an echo tool — neither of which touches the network,
the filesystem, or the environment.
"""

from __future__ import annotations

import ast
import operator
from typing import TYPE_CHECKING

from executionkit.types import Tool

if TYPE_CHECKING:
    from collections.abc import Callable

# Only these AST node operators are evaluatable — everything else is rejected.
_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluate_node(node: ast.expr) -> float:
    """Recursively evaluate a restricted arithmetic AST node.

    Only numeric constants and the operators in :data:`_BINARY_OPERATORS` /
    :data:`_UNARY_OPERATORS` are permitted. Any other node (names, calls,
    attribute access, comprehensions, etc.) raises ``ValueError`` so no
    arbitrary code can execute.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](
            _evaluate_node(node.left), _evaluate_node(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand))
    raise ValueError("Unsupported expression element")


def _safe_eval(expression: str) -> float:
    """Evaluate a numeric arithmetic expression without ``eval``/``exec``."""
    tree = ast.parse(expression, mode="eval")
    return _evaluate_node(tree.body)


async def _calculator(expression: str) -> str:
    """Evaluate an arithmetic *expression* and return the numeric result."""
    try:
        return str(_safe_eval(expression))
    except Exception:
        # Return an error string (never raise) so the tool result becomes a
        # bounded observation rather than aborting the loop. The message is
        # generic to avoid echoing attacker-controlled input verbatim.
        return "Error: could not evaluate expression"


async def _echo(text: str) -> str:
    """Return *text* unchanged — a trivial, obviously-safe demo tool."""
    return text


calculator_tool = Tool(
    name="calculator",
    description=(
        "Evaluate a numeric arithmetic expression and return the result. "
        "Supports + - * / % and ** on numbers only; no variables or functions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "An arithmetic expression, e.g. '17 * 83' or '2 ** 10'.",
            },
        },
        "required": ["expression"],
        "additionalProperties": False,
    },
    execute=_calculator,
    timeout=5.0,
)

echo_tool = Tool(
    name="echo",
    description="Return the provided text unchanged.",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to echo back verbatim.",
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    execute=_echo,
    timeout=5.0,
)

DEMO_TOOLS: tuple[Tool, ...] = (calculator_tool, echo_tool)
"""The complete, fixed toolset the ``react_loop`` MCP tool exposes."""
