"""React-loop pattern: think-act-observe tool-calling loop."""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import logging
from collections.abc import Callable, Mapping
from itertools import chain
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from executionkit._constants import DEFAULT_MAX_TOKENS
from executionkit.approval import ApprovalGate, ApprovalRequest
from executionkit.cost import CostTracker
from executionkit.engine.messages import (
    assistant_message,
    assistant_tool_calls_message,
    system_message,
    user_message,
)
from executionkit.engine.parallel import gather_resilient
from executionkit.engine.retry import RetryConfig  # noqa: TC001
from executionkit.observability import TraceCallback, TraceEvent, emit_trace
from executionkit.patterns.base import (
    _note_truncation,
    checked_complete,
    run_checkpoint,
)
from executionkit.provider import (
    MaxIterationsError,
    ToolCallingProvider,
    _provider_supports_tools,
)
from executionkit.types import PatternResult, TerminationReason, TokenUsage, Tool

if TYPE_CHECKING:
    from collections.abc import Awaitable, Sequence

    from executionkit.types import CheckpointCallback

# ---------------------------------------------------------------------------
# Module-level defaults — named constants; no magic numbers.
# ---------------------------------------------------------------------------

_DEFAULT_MAX_ROUNDS: int = 8
_DEFAULT_MAX_OBSERVATION_CHARS: int = 12_000
_DEFAULT_TEMPERATURE: float = 0.3

# Per-round ceiling on model-requested tool calls. Everything in a round runs
# concurrently, so an unbounded round is an unbounded concurrent fan-out — a
# buggy or adversarial model requesting hundreds of calls must hit a wall.
# Generous relative to real models (typically < 10 parallel calls per turn).
_DEFAULT_MAX_TOOL_CALLS_PER_ROUND: int = 32

# Prefix prepended to the summarizer output when injected as a system message.
_SUMMARY_PREFIX: str = "Summary of earlier conversation: "

# An async callback that condenses dropped history messages into a short string.
# Receives the ordered messages trimming removed; returns either the summary text,
# or a ``(summary_text, TokenUsage)`` pair so the tokens the summarizer itself
# spent are folded into the loop's cost accounting and counted against ``max_cost``.
# Returning a bare ``str`` is treated as zero reported usage. Not exported from the
# public API — wire it via the react_loop(summarizer=...) param.
HistorySummarizer = Callable[
    ["Sequence[dict[str, Any]]"],
    "Awaitable[str | tuple[str, TokenUsage]]",
]

_JSON_SCHEMA_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_required_args(required: list[str], arguments: dict[str, Any]) -> str | None:
    """Return an error string if any required argument is missing, else None."""
    for key in required:
        if key not in arguments:
            return f"Missing required argument: '{key}'"
    return None


def _check_additional_args(
    props: dict[str, Any],
    additional: bool | dict[str, Any],
    arguments: dict[str, Any],
) -> str | None:
    """Return an error string if additionalProperties is False and an extra key
    is present, else None."""
    if additional is not False:
        return None
    for key in arguments:
        if key not in props:
            return f"Unexpected argument: '{key}' (additionalProperties is false)"
    return None


def _check_arg_type(key: str, value: Any, prop_schema: dict[str, Any]) -> str | None:
    """Return an error string if *value* does not match the JSON Schema type for
    *key*, else None.  Returns None immediately when no mapped type is declared."""
    expected_type: str | None = prop_schema.get("type")
    if not expected_type or expected_type not in _JSON_SCHEMA_TYPE_MAP:
        return None
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


# Logged at most once per process when Tier B (jsonschema) is unavailable.
_subset_validator_warned: bool = False

_JSONSCHEMA_MODULE: str = "jsonschema"


def _jsonschema_available() -> bool:
    """Return True if the optional ``jsonschema`` package can be imported.

    Detected via :func:`importlib.util.find_spec` at call time (deliberately not
    cached) so the result tracks the current environment and stays patchable in
    tests.  The lookup cost is negligible next to the LLM round-trip preceding
    each tool call.
    """
    return importlib.util.find_spec(_JSONSCHEMA_MODULE) is not None


def _warn_subset_validator_once() -> None:
    """Emit a one-time debug notice that only the Tier-A subset validator is active."""
    global _subset_validator_warned
    if not _subset_validator_warned:
        logging.getLogger(__name__).debug(
            "jsonschema not installed; using subset validator"
        )
        _subset_validator_warned = True


def _subset_validate_tool_args(
    parameters_schema: Mapping[str, Any], arguments: dict[str, Any]
) -> str | None:
    """Tier A: dependency-free subset validator.

    Checks required fields, ``additionalProperties: false``, and top-level
    property types.  Returns None if valid, or an error string otherwise.
    """
    props: dict[str, Any] = parameters_schema.get("properties", {})
    required: list[str] = parameters_schema.get("required", [])
    additional: bool | dict[str, Any] = parameters_schema.get(
        "additionalProperties", True
    )

    error = _check_required_args(required, arguments)
    if error is not None:
        return error

    error = _check_additional_args(props, additional, arguments)
    if error is not None:
        return error

    for key, value in arguments.items():
        if key not in props:
            continue
        error = _check_arg_type(key, value, props[key])
        if error is not None:
            return error

    return None


def _jsonschema_validate_tool_args(
    parameters_schema: Mapping[str, Any], arguments: dict[str, Any]
) -> str | None:
    """Tier B: full JSON Schema validation via the optional ``jsonschema`` package.

    Covers what Tier A cannot express: nested objects, ``enum``,
    ``minimum``/``maximum``, ``minLength``/``maxLength``, ``pattern``, and
    ``anyOf``/``oneOf``.  A ``ValidationError`` (bad *arguments*) becomes an error
    string; a ``SchemaError`` (a malformed *tool schema*) is logged and treated as
    "no additional error" so a buggy schema cannot crash the loop.
    """
    import jsonschema  # local import: only reached when the extra is installed

    # ToolCall wraps its arguments in a MappingProxyType, which jsonschema does
    # not recognise as a JSON "object" (it type-checks against ``dict``).  Pass a
    # plain dict so a real tool call is not spuriously rejected; nested values are
    # already plain dicts (JSON-parsed), so a shallow copy is sufficient.
    try:
        jsonschema.validate(instance=dict(arguments), schema=dict(parameters_schema))
    except jsonschema.ValidationError as exc:
        return str(exc.message)
    except jsonschema.SchemaError as exc:
        logging.getLogger(__name__).warning(
            "Invalid tool parameter schema; skipping jsonschema validation: %s",
            exc.message,
        )
    return None


_TIER_A_UNEXPRESSIBLE: tuple[str, ...] = (
    "enum",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "anyOf",
    "oneOf",
    "allOf",
)


def _schema_needs_tier_b(schema: Any, *, is_top_level: bool = True) -> bool:
    """Return True if *schema* (recursively) uses a constraint Tier A cannot check.

    Tier A's ``_subset_validate_tool_args`` is a flat, single-level validator:
    it only checks required fields, ``additionalProperties: false``, and
    property types at the TOP level of the schema — it never descends into
    nested ``object`` properties, and ``_check_arg_type`` never inspects
    ``items`` at all (it only confirms the property itself is a ``list``). So
    any ``required``/``additionalProperties``/``properties`` below the top
    level, or ANY ``items`` constraint at any level (even a plain scalar
    type), is silently unchecked by Tier A — on top of the top-level-only
    ``enum``/bounds/``pattern``/combinator gap. This walks the schema looking
    for any of those constraints so the caller can fail closed instead of
    silently accepting arguments Tier A rubber-stamps.

    JSON Schema (draft 6+) also permits a bare boolean as a (sub)schema:
    ``True`` accepts anything (trivially satisfied, no Tier B needed) and
    ``False`` rejects everything (which Tier A cannot enforce, so Tier B is
    needed). A malformed, non-Mapping/non-bool schema is treated the same as
    ``False`` — fail closed rather than crash.
    """
    if not isinstance(schema, Mapping):
        return schema is not True
    nested_only_keys = ("properties", "required", "additionalProperties")
    if any(key in schema for key in _TIER_A_UNEXPRESSIBLE):
        return True
    if not is_top_level and any(key in schema for key in nested_only_keys):
        return True
    if "items" in schema:
        return True
    properties = schema.get("properties")
    return (
        (schema.get("type") == "object" or "properties" in schema)
        and isinstance(properties, Mapping)
        and any(
            _schema_needs_tier_b(prop_schema, is_top_level=False)
            for prop_schema in properties.values()
        )
    )


def _validate_tool_args(
    parameters_schema: Mapping[str, Any], arguments: dict[str, Any]
) -> str | None:
    """Validate tool-call *arguments* against the tool's JSON Schema.

    Two tiers run in order:

    * **Tier A** (always available): the dependency-free subset validator.
    * **Tier B** (when ``jsonschema`` is installed): full JSON Schema validation
      for the constraints Tier A cannot express.

    When ``jsonschema`` is not installed and the schema uses a constraint Tier A
    cannot express (see :data:`_TIER_A_UNEXPRESSIBLE`), this fails closed with
    an actionable error rather than silently accepting arguments that were
    never actually checked against that constraint.

    Returns None if the arguments are valid, otherwise an error string suitable
    for surfacing to the model as a tool observation.
    """
    error = _subset_validate_tool_args(parameters_schema, arguments)
    if error is not None:
        return error
    if _jsonschema_available():
        return _jsonschema_validate_tool_args(parameters_schema, arguments)
    _warn_subset_validator_once()
    if _schema_needs_tier_b(parameters_schema):
        return (
            "Tool schema uses a constraint the built-in validator cannot check "
            "(e.g. enum/minimum/maximum/pattern) and the optional 'jsonschema' "
            "package is not installed; install it with "
            "'pip install executionkit[jsonschema]' to validate this schema"
        )
    return None


_TRUNCATION_MARKER = "\n[truncated]"


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to at most ``max_chars`` chars, appending a marker if trimmed.

    When the limit is smaller than the truncation marker itself, return the
    leading slice of the original text instead of a partial marker.
    """
    if len(text) <= max_chars:
        return text
    if max_chars <= len(_TRUNCATION_MARKER):
        return text[:max_chars]
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


def _split_summary_result(
    result: str | tuple[str, TokenUsage],
) -> tuple[str, TokenUsage]:
    """Normalise a summarizer return into ``(summary_text, reported_usage)``.

    A summarizer may return a bare string (no usage reported, counted as zero)
    or a ``(text, TokenUsage)`` pair so the tokens it spent are accounted.
    """
    if isinstance(result, tuple):
        return result[0], result[1]
    return result, TokenUsage()


async def _summarize_trimmed_window(
    history: list[dict[str, Any]],
    active_messages: list[dict[str, Any]],
    summarizer: HistorySummarizer,
    tracker: CostTracker,
    summary_cache: dict[int, str],
) -> list[dict[str, Any]]:
    """Return a new active window with a summary of the dropped messages injected.

    ``_trim_messages`` keeps ``history[0]`` plus a recent tail, so the dropped
    messages are the contiguous slice between the preserved first message and
    that tail. Because *history* only ever grows by appending, that slice is a
    stable prefix identified solely by its end boundary, so the boundary indexes
    *summary_cache*: a window whose boundary is unchanged across rounds reuses
    the cached summary and the *summarizer* is not called again.

    On a cache miss the dropped messages are passed (in order) to *summarizer*;
    any :class:`~executionkit.types.TokenUsage` it reports is folded into
    *tracker* so the next round's budget check counts it against ``max_cost``.
    The summary is inserted as a system message right after the first message.
    *history* and the caller's *active_messages* are not mutated — a fresh list
    is returned.
    """
    kept_tail_len = len(active_messages) - 1
    boundary = len(history) - kept_tail_len
    summary_text = summary_cache.get(boundary)
    if summary_text is None:
        dropped = history[1:boundary]
        summary_text, reported_usage = _split_summary_result(await summarizer(dropped))
        tracker.add_usage(reported_usage)
        summary_cache[boundary] = summary_text
    return [
        active_messages[0],
        system_message(_SUMMARY_PREFIX + summary_text),
        *active_messages[1:],
    ]


def _validate_react_loop_args(
    provider: ToolCallingProvider,
    max_rounds: int,
    max_observation_chars: int,
    tool_timeout: float | None,
    max_tokens: int,
    max_history_messages: int | None,
    max_tool_calls_per_round: int,
) -> None:
    """Raise ValueError / TypeError for invalid react_loop arguments."""
    if not _provider_supports_tools(provider):
        raise TypeError(
            "react_loop() requires a ToolCallingProvider. "
            "Ensure the provider has supports_tools = True."
        )
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be >= 1, got {max_rounds}")
    if max_tool_calls_per_round < 1:
        raise ValueError(
            f"max_tool_calls_per_round must be >= 1, got {max_tool_calls_per_round}"
        )
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


def _seed_messages(
    prompt: str | None, messages: Sequence[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Return the initial conversation list from *prompt* xor *messages*.

    Exactly one of *prompt* / *messages* must be supplied. The result is always
    a fresh ``list`` copy, so a caller's *messages* are never mutated by the loop.
    """
    if prompt is not None and messages is not None:
        raise ValueError("react_loop() accepts prompt or messages, not both")
    if messages is not None:
        if not messages:
            raise ValueError("react_loop() messages must be non-empty")
        return list(messages)
    if prompt is None:
        raise ValueError("react_loop() requires either prompt or messages")
    return [user_message(prompt)]


def _build_assistant_message(response: Any) -> dict[str, Any]:
    """Build the assistant-role message dict from an LLM response with tool calls."""
    return assistant_tool_calls_message(response.content, response.tool_calls)


async def _execute_tool_calls_round(
    tool_calls: Any,
    tool_lookup: dict[str, Tool],
    tool_timeout: float | None,
    max_observation_chars: int,
    metadata: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    max_tool_calls_per_round: int = _DEFAULT_MAX_TOOL_CALLS_PER_ROUND,
    trace: TraceCallback | None = None,
    approval_gate: ApprovalGate | None = None,
    redact_trace_args: bool = True,
) -> None:
    """Execute one round's tool calls concurrently, appending observations.

    Tool calls within a round are independent, so they run concurrently via
    ``asyncio.gather``; results are then applied in the original request order
    so the conversation and metadata stay deterministic. Mutates *metadata*
    (tool_calls_made, truncated_observations) and *messages* in place — both are
    owned by the caller (react_loop). ``_execute_tool_call`` never raises (it
    returns error strings), so one failing tool cannot abort the round.

    When *approval_gate* is supplied, each call is checked before its body runs;
    a denial becomes a bounded observation instead of executing the tool. When
    *trace* is supplied, ``tool_call_start``/``tool_call_end`` events are emitted
    around each call. Both run inside the concurrent fan-out, so trace events may
    interleave across calls; metadata is still applied in request order below.

    When *redact_trace_args* is ``True`` (the default), argument *values* are
    omitted from ``tool_call_start`` trace events; only the argument *keys* are
    included.  Set to ``False`` to include raw argument values (useful in
    controlled test environments, but risks leaking PII or secrets into traces).
    """

    async def _run_one(tc: Any) -> tuple[Any, str]:
        # Build the trace payload for tool_call_start.
        # When redaction is enabled (the safe default), emit only argument keys
        # so traces remain useful for debugging without leaking argument values
        # (which may contain PII, credentials, or other sensitive data).
        if redact_trace_args:
            trace_args: dict[str, Any] = dict.fromkeys(tc.arguments, "[redacted]")
        else:
            trace_args = dict(tc.arguments)
        await emit_trace(
            trace,
            TraceEvent.create(
                "tool_call_start",
                {
                    "tool_name": tc.name,
                    "tool_call_id": tc.id,
                    "arguments": trace_args,
                },
            ),
        )
        decision = (
            await approval_gate.request(
                ApprovalRequest.create(
                    "tool_call",
                    tc.name,
                    {"tool_call_id": tc.id, "arguments": tc.arguments},
                )
            )
            if approval_gate is not None
            else None
        )
        if decision is not None and not decision.approved:
            suffix = f": {decision.reason}" if decision.reason else ""
            observation = f"Tool '{tc.name}' blocked by approval{suffix}"
        else:
            observation = await _execute_tool_call(
                tc_name=tc.name,
                tc_arguments=tc.arguments,
                tool_lookup=tool_lookup,
                tool_timeout=tool_timeout,
                max_observation_chars=max_observation_chars,
            )
        await emit_trace(
            trace,
            TraceEvent.create(
                "tool_call_end",
                {
                    "tool_name": tc.name,
                    "tool_call_id": tc.id,
                    "blocked": decision is not None and not decision.approved,
                },
            ),
        )
        return tc, observation

    # Materialize once so the gather and the result loop iterate the same order.
    all_calls = list(tool_calls)
    # Bound the concurrent fan-out: everything past the per-round cap is never
    # executed — it still receives a tool-role rejection observation below so
    # the conversation stays well-formed (every tool_call_id must be answered),
    # and the model can retry with fewer calls next round.
    calls = all_calls[:max_tool_calls_per_round]
    rejected_calls = all_calls[max_tool_calls_per_round:]
    # gather_resilient (return_exceptions=True): an UNEXPECTED raise inside a single
    # _run_one (e.g. an approval-gate or trace error) surfaces as a per-tool failure
    # rather than cancelling every sibling tool in the round. _run_one already maps
    # tool-execution errors to observation strings, so this only catches the
    # unexpected. Order is preserved, so results[i] pairs with calls[i].
    results = await gather_resilient([_run_one(tc) for tc in calls])

    for tc, result in zip(calls, results, strict=True):
        if isinstance(result, BaseException):
            # Control-flow exceptions (CancelledError, KeyboardInterrupt,
            # SystemExit) are BaseException but not Exception — they must
            # propagate, never become a tool observation. gather_resilient
            # returns a child CancelledError as a value (return_exceptions=True),
            # so re-raise it here rather than stringifying it.
            if not isinstance(result, Exception):
                raise result
            observation = f"Tool '{tc.name}' failed: {type(result).__name__}"
        else:
            _, observation = result
        metadata["tool_calls_made"] = int(metadata["tool_calls_made"]) + 1
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

    # Rejected surplus calls were never executed (no start/end trace events);
    # each still gets a tool-role answer so the transcript stays well-formed.
    for tc in rejected_calls:
        metadata["rejected_tool_calls"] = int(metadata["rejected_tool_calls"]) + 1
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": (
                    f"Tool call rejected: this round requested {len(all_calls)} "
                    f"tool calls, exceeding the limit of "
                    f"{max_tool_calls_per_round}. Retry with fewer calls."
                ),
            }
        )


async def react_loop(
    provider: ToolCallingProvider,
    prompt: str | None = None,
    tools: Sequence[Tool] = (),
    *,
    messages: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = _DEFAULT_MAX_ROUNDS,
    max_observation_chars: int = _DEFAULT_MAX_OBSERVATION_CHARS,
    tool_timeout: float | None = None,
    max_tool_calls_per_round: int = _DEFAULT_MAX_TOOL_CALLS_PER_ROUND,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
    max_history_messages: int | None = None,
    trace: TraceCallback | None = None,
    approval_gate: ApprovalGate | None = None,
    redact_trace_args: bool = True,
    on_checkpoint: CheckpointCallback | None = None,
    summarizer: HistorySummarizer | None = None,
) -> PatternResult[str]:
    """Execute a think-act-observe tool-calling loop.

    The LLM is called repeatedly with the conversation history and
    available tool schemas.  When the LLM returns tool calls, each tool
    is executed and its result appended as a tool-role message.  The loop
    ends when the LLM responds without tool calls (final answer) or
    ``max_rounds`` is exhausted.

    Supply **either** *prompt* (a single new user turn) **or** *messages* (a
    full prior conversation to continue), not both.  Passing *messages* enables
    multi-turn assistants: the returned ``metadata["messages"]`` holds the
    complete updated transcript (the input history plus this run's assistant
    turns, tool results, and final answer) ready to feed into the next call.

    Args:
        provider: LLM provider to call.
        prompt: Initial user prompt. Sugar for ``messages=[user_message(prompt)]``;
            mutually exclusive with *messages*.
        tools: Sequence of :class:`Tool` definitions available to the LLM.
        messages: A prior conversation (OpenAI-format message dicts) to continue
            instead of starting from *prompt*. The list is copied, never mutated.
        max_rounds: Maximum think-act-observe cycles.
        max_observation_chars: Truncation limit for each tool result.
        tool_timeout: Per-call timeout override.  Falls back to
            ``tool.timeout`` if ``None``.
        max_tool_calls_per_round: Ceiling on model-requested tool calls
            executed in a single round (they run concurrently, so this bounds
            the fan-out). Surplus calls are never executed; each receives a
            rejection observation telling the model to retry with fewer.
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens per LLM completion.
        max_cost: Optional token/call budget.
        retry: Optional retry configuration per LLM call.
        max_history_messages: When set, trim the message history to at most
            this many entries before each LLM call. Always keeps the first
            message (the original prompt). ``None`` disables trimming.
        trace: Optional structured trace callback.
        approval_gate: Optional gate checked before each tool execution.
        redact_trace_args: When ``True`` (the default), argument *values* are
            replaced with ``"[redacted]"`` in ``tool_call_start`` trace events.
            Only argument *keys* are emitted, keeping traces useful for
            debugging without risking PII or credential leakage.  Set to
            ``False`` to include raw argument values (e.g. in controlled test
            environments).
        on_checkpoint: Optional callback invoked after each round that dispatched
            tool calls, receiving ``(round, state)`` where ``round`` is 0-based
            and ``state`` is a JSON-serializable dict with keys ``round``,
            ``last_response``, ``tool_calls_made`` (list of tool names),
            ``cost``, and ``messages`` (the full transcript so far, a list of
            message dicts). May be sync or async; exceptions are logged and
            swallowed so a failing checkpoint never aborts the loop.
        summarizer: Optional async callback used together with
            ``max_history_messages``. When trimming drops earlier messages, the
            dropped messages (in order) are passed to ``summarizer`` and the
            returned text is injected as a system message into the *per-round*
            window sent to the provider, immediately after the preserved first
            message. The stored transcript is never modified — only the active
            window. ``None`` (the default) disables summarization, leaving
            trimming behaviour unchanged.

            The callback may return either the summary text or a
            ``(text, TokenUsage)`` pair; reported usage is folded into the
            loop's cost accounting and counted against ``max_cost`` on the
            following round. Summaries are memoized by the dropped-window
            boundary, so a window that is unchanged across rounds is summarized
            at most once rather than re-summarized each round.

    Returns:
        A :class:`PatternResult` whose ``value`` is the final LLM
        response, ``score`` is ``None``, and ``metadata`` includes
        ``rounds`` and ``tool_calls_made``.

    Metadata:
        rounds (int): Number of think-act-observe cycles completed.
        tool_calls_made (int): Total individual tool invocations.
        rejected_tool_calls (int): Model-requested calls never executed because
            a round exceeded ``max_tool_calls_per_round``.
        truncated_responses (int): LLM responses truncated due to
            ``finish_reason=length``.
        truncated_observations (int): Tool results truncated due to
            ``max_observation_chars``.
        messages_trimmed (int): Number of rounds where history was trimmed.
        summarized (int): Number of rounds where trimming dropped messages and a
            ``summarizer`` was supplied, so an earlier-conversation summary was
            injected into that round's active window. Always 0 when no
            ``summarizer`` is provided.
        messages (tuple[dict, ...]): The full conversation transcript after the
            loop, including the seeded input, every assistant/tool turn, and the
            final assistant answer. Feed back in via ``messages=`` to continue.
        termination_reason (TerminationReason | None): How the loop ended.
            ``TerminationReason.NATURAL`` when the LLM returned a final
            answer; ``TerminationReason.MAX_ITERATIONS`` when ``max_rounds``
            was exhausted (also present on the raised
            :exc:`~executionkit.provider.MaxIterationsError`'s ``.metadata``).
            ``None`` only during error paths that abort early.
    """
    _validate_react_loop_args(
        provider,
        max_rounds,
        max_observation_chars,
        tool_timeout,
        max_tokens,
        max_history_messages,
        max_tool_calls_per_round,
    )
    tracker = CostTracker()
    metadata: dict[str, Any] = {
        "rounds": 0,
        "tool_calls_made": 0,
        "rejected_tool_calls": 0,
        "truncated_responses": 0,
        "truncated_observations": 0,
        "messages_trimmed": 0,
        "summarized": 0,
        "termination_reason": None,
    }
    tool_schemas = [tool.to_schema() for tool in tools]
    tool_lookup: dict[str, Tool] = {tool.name: tool for tool in tools}
    history = _seed_messages(prompt, messages)
    # Memoizes summaries by dropped-window boundary so a stable window is
    # summarized at most once even when trimming recurs across rounds.
    summary_cache: dict[int, str] = {}

    for round_num in range(1, max_rounds + 1):
        if max_history_messages is not None:
            active_messages = _trim_messages(history, max_history_messages)
            if len(active_messages) < len(history):
                metadata["messages_trimmed"] = int(metadata["messages_trimmed"]) + 1
                if summarizer is not None:
                    active_messages = await _summarize_trimmed_window(
                        history,
                        active_messages,
                        summarizer,
                        tracker,
                        summary_cache,
                    )
                    metadata["summarized"] = int(metadata["summarized"]) + 1
        else:
            active_messages = history
        response = await checked_complete(
            provider,
            active_messages,
            tracker,
            max_cost,
            retry,
            trace,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tool_schemas,
        )
        _note_truncation(response, metadata, "react_loop")
        metadata["rounds"] = round_num

        # No tool calls means the LLM is done — return the content.
        if not response.has_tool_calls:
            metadata["termination_reason"] = TerminationReason.NATURAL
            history.append(assistant_message(response.content))
            return PatternResult[str](
                value=response.content,
                score=None,
                cost=tracker.to_usage(),
                metadata=MappingProxyType({**metadata, "messages": tuple(history)}),
            )

        # Append assistant message with tool calls to conversation
        history.append(_build_assistant_message(response))

        # Execute each tool call and append results
        await _execute_tool_calls_round(
            response.tool_calls,
            tool_lookup,
            tool_timeout,
            max_observation_chars,
            metadata,
            history,
            max_tool_calls_per_round=max_tool_calls_per_round,
            trace=trace,
            approval_gate=approval_gate,
            redact_trace_args=redact_trace_args,
        )

        if on_checkpoint is not None:
            checkpoint_state: dict[str, Any] = {
                "round": round_num - 1,
                "last_response": response.content,
                "tool_calls_made": [tc.name for tc in response.tool_calls],
                "cost": dataclasses.asdict(tracker.snapshot()),
                "messages": list(history),
            }
            await run_checkpoint(
                on_checkpoint, round_num - 1, checkpoint_state, context="react_loop"
            )

    metadata["termination_reason"] = TerminationReason.MAX_ITERATIONS
    metadata["messages"] = tuple(history)
    raise MaxIterationsError(
        "react_loop() reached max_rounds without a final answer",
        cost=tracker.to_usage(),
        metadata=dict(metadata),
    )


async def _execute_tool_call(
    *,
    tc_name: str,
    tc_arguments: dict[str, Any],
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
        # exc_info=False: tracebacks can carry tool arguments, URLs, or
        # credentials; the exception type in the message is sufficient signal.
        logging.getLogger(__name__).debug(
            "Tool '%s' raised %s", tc_name, type(exc).__name__, exc_info=False
        )
        return f"Tool '{tc_name}' failed: {type(exc).__name__}"
