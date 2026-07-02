"""Tool definitions and dispatch for the ExecutionKit MCP server.

Exposes two ExecutionKit patterns as MCP tools:

* ``consensus`` — parallel sampling with majority/unanimous voting.
* ``react_loop`` — a think-act-observe tool loop restricted to a fixed,
  side-effect-free demo toolset (calculator + echo). MCP callers cannot
  register arbitrary Python callables (ADR-012).

Provider wiring reuses the ``EXECUTIONKIT_*`` env-var conventions from
:func:`executionkit.evals.live_provider_from_env` (``EXECUTIONKIT_BASE_URL``,
``EXECUTIONKIT_MODEL``, ``EXECUTIONKIT_API_KEY``). When the required env vars
are absent, tool calls return a well-formed *error result* (``isError: True``)
explaining what is missing — the server never crashes on missing config.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from executionkit.mcp._constants import (
    DEFAULT_CONSENSUS_SAMPLES,
    DEFAULT_REACT_ROUNDS,
    MAX_CONSENSUS_SAMPLES,
    MAX_REACT_ROUNDS,
    MAX_TEMPERATURE,
    MIN_CONSENSUS_SAMPLES,
    MIN_REACT_ROUNDS,
    MIN_TEMPERATURE,
)
from executionkit.mcp._demo_tools import DEMO_TOOLS
from executionkit.patterns.consensus import consensus
from executionkit.patterns.react_loop import react_loop
from executionkit.provider import LLMProvider, Provider, ToolCallingProvider
from executionkit.types import PatternResult, VotingStrategy

# A provider factory returns a live provider or ``None`` when unconfigured.
# Injectable so tests can substitute a MockProvider without env vars or network.
ProviderFactory = Callable[[], "LLMProvider | None"]

# A tool handler receives parsed arguments plus the resolved provider factory
# and returns the text payload for a successful ``tools/call`` result.
ToolHandler = Callable[[Mapping[str, Any], ProviderFactory], Awaitable[str]]

_MISSING_PROVIDER_MESSAGE: str = (
    "No LLM provider is configured. Set EXECUTIONKIT_BASE_URL and "
    "EXECUTIONKIT_MODEL (and optionally EXECUTIONKIT_API_KEY) in the server's "
    "environment, then restart the MCP server."
)


class ToolExecutionError(Exception):
    """Raised by a tool handler to signal a tool-level failure.

    The server maps this to an MCP result with ``isError: True`` and the
    message as text — *not* to a JSON-RPC error — so tool failures surface to
    the model as an error result it can reason about, per the MCP spec.
    """


def provider_from_env() -> LLMProvider | None:
    """Build a :class:`~executionkit.provider.Provider` from ``EXECUTIONKIT_*``.

    Mirrors the env-var conventions of
    :func:`executionkit.evals.live_provider_from_env` (minus the
    ``EXECUTIONKIT_LIVE_EVAL`` opt-in gate, which is an eval-suite concern):
    ``EXECUTIONKIT_BASE_URL`` and ``EXECUTIONKIT_MODEL`` are required;
    ``EXECUTIONKIT_API_KEY`` is optional and defaults to an empty string.

    Returns ``None`` when either required variable is missing so the server can
    start and answer ``initialize`` / ``tools/list`` regardless of config, and
    only surface the misconfiguration at ``tools/call`` time.
    """
    base_url = os.getenv("EXECUTIONKIT_BASE_URL")
    model = os.getenv("EXECUTIONKIT_MODEL")
    if not base_url or not model:
        return None
    return Provider(
        base_url=base_url,
        model=model,
        api_key=os.getenv("EXECUTIONKIT_API_KEY", ""),
    )


def _require_provider(provider_factory: ProviderFactory) -> LLMProvider:
    """Return a provider from *provider_factory*, else raise ToolExecutionError."""
    provider = provider_factory()
    if provider is None:
        raise ToolExecutionError(_MISSING_PROVIDER_MESSAGE)
    return provider


def _clamp_int(value: Any, *, low: int, high: int, default: int, field: str) -> int:
    """Coerce *value* to an int within ``[low, high]``.

    ``None`` yields *default*. A non-integer (or out-of-range) value raises
    :class:`ToolExecutionError` so the caller gets an actionable error result
    rather than a silently-mangled argument.
    """
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolExecutionError(f"'{field}' must be an integer")
    if value < low or value > high:
        raise ToolExecutionError(f"'{field}' must be between {low} and {high}")
    return value


def _clamp_temperature(value: Any) -> float | None:
    """Validate an optional ``temperature`` argument, returning ``None`` if unset."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolExecutionError("'temperature' must be a number")
    temperature = float(value)
    if temperature < MIN_TEMPERATURE or temperature > MAX_TEMPERATURE:
        raise ToolExecutionError(
            f"'temperature' must be between {MIN_TEMPERATURE} and {MAX_TEMPERATURE}"
        )
    return temperature


def _require_prompt(arguments: Mapping[str, Any]) -> str:
    """Extract and validate the required non-empty string ``prompt`` argument."""
    prompt = arguments.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ToolExecutionError("'prompt' is required and must be a non-empty string")
    return prompt


def _format_consensus_result(result: PatternResult[str]) -> str:
    """Render a consensus :class:`PatternResult` as human-readable tool text."""
    agreement = result.metadata.get("agreement_ratio")
    unique = result.metadata.get("unique_responses")
    cost = result.cost
    lines = [
        result.value,
        "",
        f"agreement_ratio: {agreement}",
        f"unique_responses: {unique}",
        (
            f"cost: input_tokens={cost.input_tokens} "
            f"output_tokens={cost.output_tokens} llm_calls={cost.llm_calls}"
        ),
    ]
    return "\n".join(lines)


def _format_react_result(result: PatternResult[str]) -> str:
    """Render a react_loop :class:`PatternResult` as human-readable tool text."""
    cost = result.cost
    lines = [
        result.value,
        "",
        f"rounds: {result.metadata.get('rounds')}",
        f"tool_calls_made: {result.metadata.get('tool_calls_made')}",
        (
            f"cost: input_tokens={cost.input_tokens} "
            f"output_tokens={cost.output_tokens} llm_calls={cost.llm_calls}"
        ),
    ]
    return "\n".join(lines)


async def _handle_consensus(
    arguments: Mapping[str, Any], provider_factory: ProviderFactory
) -> str:
    """Run :func:`~executionkit.consensus` from parsed MCP tool arguments."""
    provider = _require_provider(provider_factory)
    prompt = _require_prompt(arguments)
    num_samples = _clamp_int(
        arguments.get("n"),
        low=MIN_CONSENSUS_SAMPLES,
        high=MAX_CONSENSUS_SAMPLES,
        default=DEFAULT_CONSENSUS_SAMPLES,
        field="n",
    )
    temperature = _clamp_temperature(arguments.get("temperature"))

    strategy_arg = arguments.get("strategy", VotingStrategy.MAJORITY.value)
    try:
        strategy = VotingStrategy(strategy_arg)
    except ValueError as exc:
        raise ToolExecutionError(
            "'strategy' must be 'majority' or 'unanimous'"
        ) from exc

    kwargs: dict[str, Any] = {"num_samples": num_samples, "strategy": strategy}
    if temperature is not None:
        kwargs["temperature"] = temperature

    result = await consensus(provider, prompt, **kwargs)
    return _format_consensus_result(result)


async def _handle_react_loop(
    arguments: Mapping[str, Any], provider_factory: ProviderFactory
) -> str:
    """Run :func:`~executionkit.react_loop` with the fixed demo toolset only."""
    provider = _require_provider(provider_factory)
    if not isinstance(provider, ToolCallingProvider) or not getattr(
        provider, "supports_tools", False
    ):
        raise ToolExecutionError(
            "The configured provider does not support tool calling, which "
            "react_loop requires."
        )
    prompt = _require_prompt(arguments)
    max_rounds = _clamp_int(
        arguments.get("max_rounds"),
        low=MIN_REACT_ROUNDS,
        high=MAX_REACT_ROUNDS,
        default=DEFAULT_REACT_ROUNDS,
        field="max_rounds",
    )
    result = await react_loop(
        provider,
        prompt,
        tools=DEMO_TOOLS,
        max_rounds=max_rounds,
    )
    return _format_react_result(result)


# ---------------------------------------------------------------------------
# Tool registry — definition (name, description, JSON-Schema inputSchema) plus
# the async handler. tools/list serialises the definitions; tools/call dispatches
# to the handler.
# ---------------------------------------------------------------------------


def _tool_definitions() -> tuple[dict[str, Any], ...]:
    """Return the MCP tool definitions for ``tools/list`` (JSON-Schema inputs)."""
    strategy_values = [strategy.value for strategy in VotingStrategy]
    return (
        {
            "name": "consensus",
            "description": (
                "Run N parallel LLM samples for a prompt and return the "
                "majority (or unanimous) answer with an agreement ratio."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt sent identically to every sample.",
                    },
                    "n": {
                        "type": "integer",
                        "minimum": MIN_CONSENSUS_SAMPLES,
                        "maximum": MAX_CONSENSUS_SAMPLES,
                        "default": DEFAULT_CONSENSUS_SAMPLES,
                        "description": "Number of parallel samples to draw.",
                    },
                    "strategy": {
                        "type": "string",
                        "enum": strategy_values,
                        "default": VotingStrategy.MAJORITY.value,
                        "description": "Voting strategy: majority or unanimous.",
                    },
                    "temperature": {
                        "type": "number",
                        "minimum": MIN_TEMPERATURE,
                        "maximum": MAX_TEMPERATURE,
                        "description": "Optional sampling temperature override.",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        {
            "name": "react_loop",
            "description": (
                "Run a think-act-observe reasoning loop over a fixed, "
                "side-effect-free demo toolset (a calculator and an echo tool). "
                "Arbitrary tools cannot be registered by the caller."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The task for the reasoning loop to solve.",
                    },
                    "max_rounds": {
                        "type": "integer",
                        "minimum": MIN_REACT_ROUNDS,
                        "maximum": MAX_REACT_ROUNDS,
                        "default": DEFAULT_REACT_ROUNDS,
                        "description": "Maximum think-act-observe cycles.",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
    )


_HANDLERS: dict[str, ToolHandler] = {
    "consensus": _handle_consensus,
    "react_loop": _handle_react_loop,
}


def list_tools() -> list[dict[str, Any]]:
    """Return the tool definitions for a ``tools/list`` response."""
    return [dict(definition) for definition in _tool_definitions()]


def get_handler(name: str) -> ToolHandler | None:
    """Return the async handler for tool *name*, or ``None`` if unknown."""
    return _HANDLERS.get(name)
