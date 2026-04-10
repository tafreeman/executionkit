"""React-loop pattern: think-act-observe tool-calling loop."""

from __future__ import annotations

import asyncio
import json
from itertools import chain
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from executionkit.cost import CostTracker
from executionkit.engine.retry import RetryConfig  # noqa: TC001
from executionkit.patterns.base import _note_truncation, checked_complete
from executionkit.provider import (
    MaxIterationsError,
    ToolCallingProvider,
)
from executionkit.types import PatternResult, TokenUsage, Tool

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_JSON_SCHEMA_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _validate_tool_args(
    parameters_schema: Mapping[str, Any], arguments: dict[str, Any]
) -> str | None:
    """Return None if valid, or an error string describing the problem."""
    props: dict[str, Any] = parameters_schema.get("properties", {})
    required: list[str] = parameters_schema.get("required", [])
    additional: bool | dict[str, Any] = parameters_schema.get(
        "additionalProperties", True
    )

    for key in required:
        if key not in arguments:
            return f"Missing required argument: '{key}'"

    if additional is False:
        for key in arguments:
            if key not in props:
                return f"Unexpected argument: '{key}' (additionalProperties is false)"

    for key, value in arguments.items():
        if key in props:
            expected_type = props[key].get("type")
            if expected_type and expected_type in _JSON_SCHEMA_TYPE_MAP:
                # bool is a subclass of int in Python, so isinstance(True, int) is True.
                # Reject booleans explicitly when an integer or number is expected.
                if expected_type in ("integer", "number") and isinstance(value, bool):
                    return f"Argument '{key}' expected type '{expected_type}', got bool"
                if not isinstance(value, _JSON_SCHEMA_TYPE_MAP[expected_type]):
                    return (
                        f"Argument '{key}' expected type '{expected_type}', "
                        f"got {type(value).__name__}"
                    )
    return None


_TRUNCATION_MARKER = "\n[truncated]"


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to at most ``max_chars`` chars, appending a marker if trimmed."""
    if len(text) <= max_chars:
        return text
    if max_chars <= len(_TRUNCATION_MARKER):
        return _TRUNCATION_MARKER[:max_chars]
    keep = max_chars - len(_TRUNCATION_MARKER)
    return text[:keep] + _TRUNCATION_MARKER


def _message_blocks(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group conversation history into trim-safe blocks.

    Assistant tool-call messages and their following tool results are kept in
    the same block so history trimming never splits a request/result pair.
    """
    blocks: list[list[dict[str, Any]]] = []
    message_index = 1
    while message_index < len(messages):
        message = messages[message_index]
        if message.get("role") == "assistant" and message.get("tool_calls"):
            block = [message]
            message_index += 1
            while (
                message_index < len(messages)
                and messages[message_index].get("role") == "tool"
            ):
                block.append(messages[message_index])
                message_index += 1
            blocks.append(block)
            continue
        blocks.append([message])
        message_index += 1
    return blocks


def _trim_messages(
    messages: list[dict[str, Any]], max_messages: int
) -> list[dict[str, Any]]:
    """Keep messages[0] and the most recent (max_messages - 1) entries.

    Always preserves the first message (the original user prompt).
    Returns a new list; does not mutate the input.

    Args:
        messages: The full conversation history.
        max_messages: Maximum number of messages to keep. Must be >= 1.
            A value of 1 returns only the first message.

    Raises:
        ValueError: If ``max_messages`` is less than 1.
    """
    if max_messages < 1:
        raise ValueError(f"max_messages must be >= 1, got {max_messages}")
    if max_messages == 1:
        return [messages[0]] if messages else []
    if len(messages) <= max_messages:
        return messages

    remaining = max_messages - 1
    selected_blocks: list[list[dict[str, Any]]] = []
    used = 0
    for block in reversed(_message_blocks(messages)):
        block_len = len(block)
        if used + block_len > remaining:
            break
        selected_blocks.append(block)
        used += block_len

    tail = list(chain.from_iterable(reversed(selected_blocks)))
    return [messages[0], *tail]


async def react_loop(
    provider: ToolCallingProvider,
    prompt: str,
    tools: Sequence[Tool],
    *,
    max_rounds: int = 8,
    max_observation_chars: int = 12000,
    tool_timeout: float | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
    max_history_messages: int | None = None,
    **_: Any,
) -> PatternResult[str]:
    """Execute a think-act-observe tool-calling loop.

    The LLM is called repeatedly with the conversation history and
    available tool schemas.  When the LLM returns tool calls, each tool
    is executed and its result appended as a tool-role message.  The loop
    ends when the LLM responds without tool calls (final answer) or
    ``max_rounds`` is exhausted.

    Args:
        provider: LLM provider to call.
        prompt: Initial user prompt.
        tools: Sequence of :class:`Tool` definitions available to the LLM.
        max_rounds: Maximum think-act-observe cycles.
        max_observation_chars: Truncation limit for each tool result.
        tool_timeout: Per-call timeout override.  Falls back to
            ``tool.timeout`` if ``None``.
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens per LLM completion.
        max_cost: Optional token/call budget.
        retry: Optional retry configuration per LLM call.
        max_history_messages: When set, trim the message history to at most
            this many entries before each LLM call. Always keeps the first
            message (the original prompt). ``None`` disables trimming.

    Returns:
        A :class:`PatternResult` whose ``value`` is the final LLM
        response, ``score`` is ``None``, and ``metadata`` includes
        ``rounds`` and ``tool_calls_made``.

    Metadata:
        rounds (int): Number of think-act-observe cycles completed.
        tool_calls_made (int): Total individual tool invocations.
        truncated_responses (int): LLM responses truncated due to
            ``finish_reason=length``.
        truncated_observations (int): Tool results truncated due to
            ``max_observation_chars``.
        messages_trimmed (int): Number of rounds where history was trimmed.
    """
    if not isinstance(provider, ToolCallingProvider) or not getattr(
        provider, "supports_tools", False
    ):
        raise TypeError(
            "react_loop() requires a ToolCallingProvider. "
            "Ensure the provider has supports_tools = True."
        )
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be >= 1, got {max_rounds}")
    if max_observation_chars < 1:
        raise ValueError(
            f"max_observation_chars must be >= 1, got {max_observation_chars}"
        )
    if tool_timeout is not None and tool_timeout <= 0:
        raise ValueError(f"tool_timeout must be > 0, got {tool_timeout}")
    if max_tokens < 1:
        raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")
    if max_history_messages is not None and max_history_messages < 1:
        raise ValueError(
            f"max_history_messages must be >= 1, got {max_history_messages}"
        )
    tracker = CostTracker()
    metadata: dict[str, Any] = {
        "rounds": 0,
        "tool_calls_made": 0,
        "truncated_responses": 0,
        "truncated_observations": 0,
        "messages_trimmed": 0,
    }
    tool_schemas = [tool.to_schema() for tool in tools]
    tool_lookup: dict[str, Tool] = {tool.name: tool for tool in tools}
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    for round_num in range(1, max_rounds + 1):
        if max_history_messages is not None:
            active_messages = _trim_messages(messages, max_history_messages)
            if len(active_messages) < len(messages):
                metadata["messages_trimmed"] = int(metadata["messages_trimmed"]) + 1
        else:
            active_messages = messages
        response = await checked_complete(
            provider,
            active_messages,
            tracker,
            max_cost,
            retry,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tool_schemas,
        )
        _note_truncation(response, metadata, "react_loop")
        metadata["rounds"] = round_num

        # No tool calls means the LLM is done — return the content.
        if not response.has_tool_calls:
            return PatternResult[str](
                value=response.content,
                score=None,
                cost=tracker.to_usage(),
                metadata=MappingProxyType(dict(metadata)),
            )

        # Append assistant message with tool calls to conversation
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in response.tool_calls
            ],
        }
        messages.append(assistant_msg)

        # Execute each tool call and append results
        for tc in response.tool_calls:
            metadata["tool_calls_made"] = int(metadata["tool_calls_made"]) + 1
            observation = await _execute_tool_call(
                tc_name=tc.name,
                tc_arguments=tc.arguments,
                tc_id=tc.id,
                tool_lookup=tool_lookup,
                tool_timeout=tool_timeout,
                max_observation_chars=max_observation_chars,
            )
            if observation.endswith("\n[truncated]"):
                metadata["truncated_observations"] = (
                    int(metadata["truncated_observations"]) + 1
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation,
                }
            )

    raise MaxIterationsError(
        "react_loop() reached max_rounds without a final answer",
        cost=tracker.to_usage(),
        metadata=dict(metadata),
    )


async def _execute_tool_call(
    *,
    tc_name: str,
    tc_arguments: dict[str, Any],
    tc_id: str,
    tool_lookup: dict[str, Tool],
    tool_timeout: float | None,
    max_observation_chars: int,
) -> str:
    """Execute a single tool call and return the (possibly truncated) result.

    Handles unknown tools, timeouts, and exceptions gracefully by
    returning an error description rather than propagating.

    Args:
        tc_name: Tool name requested by the LLM.
        tc_arguments: Parsed arguments for the tool.
        tc_id: The tool call identifier.
        tool_lookup: Registry mapping tool names to :class:`Tool` instances.
        tool_timeout: Per-call timeout override (``None`` uses tool default).
        max_observation_chars: Truncation limit for the result string.

    Returns:
        The tool result string, possibly truncated or an error message.
    """
    tool = tool_lookup.get(tc_name)
    if tool is None:
        return f"Error: Unknown tool '{tc_name}'"

    error = _validate_tool_args(tool.parameters, tc_arguments)
    if error is not None:
        return f"Tool '{tc_name}' argument error: {error}"

    timeout = tool_timeout if tool_timeout is not None else tool.timeout
    try:
        raw_result = await asyncio.wait_for(
            tool.execute(**tc_arguments),
            timeout=timeout,
        )
        return _truncate(str(raw_result), max_observation_chars)
    except TimeoutError:
        return f"Tool execution timed out after {timeout}s"
    except Exception as exc:
        import logging

        logging.getLogger(__name__).debug(
            "Tool '%s' raised %s", tc_name, type(exc).__name__, exc_info=True
        )
        return f"Tool '{tc_name}' failed: {type(exc).__name__}"
