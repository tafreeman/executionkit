"""Tests for the Claude Agent SDK transport.

The harness is driven by monkeypatching ``executionkit.claude_sdk.query``, so
nothing here needs the Claude Code CLI, a sign-in, or the network. The message
objects handed back are the SDK's own dataclasses rather than stand-ins, so a
field rename upstream fails these tests instead of passing them and failing in
production.

``claude-agent-sdk`` is deliberately **not** in the ``dev`` extra: it pulls
``mcp``, which pulls ``opentelemetry-api``, and the ``test`` job's whole point
is that the locked dev set has no OpenTelemetry in it. So this file skips when
the ``[claude]`` extra is absent, and the ``claude-sdk`` CI job installs the
extra and hard-guards the import so the skip can never go green unnoticed --
the same split that ``tests/test_observability.py`` and the ``observability``
job use.
"""

from __future__ import annotations

import importlib.util
import time
from typing import TYPE_CHECKING, Any

import pytest

from executionkit import ClaudeAgentProvider
from executionkit.claude_sdk import _retry_after_from, _split_messages, _text_delta
from executionkit.errors import PermanentError, ProviderError, RateLimitError
from executionkit.provider import (
    LLMProvider,
    StreamingProvider,
    ToolCallingProvider,
    _provider_supports_tools,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

_HAS_SDK = importlib.util.find_spec("claude_agent_sdk") is not None

pytestmark = pytest.mark.skipif(
    not _HAS_SDK,
    reason="requires the [claude] extra (claude-agent-sdk)",
)

if _HAS_SDK:
    from claude_agent_sdk import (
        AssistantMessage,
        RateLimitEvent,
        ResultMessage,
        StreamEvent,
        TextBlock,
    )
    from claude_agent_sdk.types import RateLimitInfo

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def assistant(text: str, *, error: str | None = None) -> AssistantMessage:
    return AssistantMessage(
        content=[TextBlock(text=text)],
        model="claude-opus-5",
        error=error,  # type: ignore[arg-type]
    )


def result(
    *,
    is_error: bool = False,
    usage: dict[str, Any] | None = None,
    cost: float | None = None,
    stop_reason: str | None = "end_turn",
    api_error_status: int | None = None,
    errors: list[str] | None = None,
) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=1,
        session_id="s1",
        stop_reason=stop_reason,
        total_cost_usd=cost,
        usage=usage,
        api_error_status=api_error_status,
        errors=errors,
    )


def rate_limit(status: str, resets_at: int | None = None) -> RateLimitEvent:
    return RateLimitEvent(
        rate_limit_info=RateLimitInfo(
            status=status,  # type: ignore[arg-type]
            resets_at=resets_at,
            rate_limit_type="five_hour",
        ),
        uuid="u1",
        session_id="s1",
    )


def delta(text: str) -> StreamEvent:
    return StreamEvent(
        uuid="u1",
        session_id="s1",
        event={
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": text},
        },
    )


def fake_query(*messages: Any) -> Any:
    """Build a ``query`` stand-in that replays *messages* and records its call."""
    calls: list[dict[str, Any]] = []

    async def _query(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        calls.append({"prompt": prompt, "options": options})
        for message in messages:
            yield message

    _query.calls = calls  # type: ignore[attr-defined]
    return _query


def patch_query(monkeypatch: pytest.MonkeyPatch, *messages: Any) -> Any:
    fake = fake_query(*messages)
    monkeypatch.setattr("executionkit.claude_sdk.query", fake)
    return fake


USER: Sequence[dict[str, Any]] = [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_satisfies_llm_and_streaming_protocols() -> None:
    provider = ClaudeAgentProvider()
    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, StreamingProvider)


def test_missing_extra_raises_with_an_install_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructing without the extra fails loudly, not at first use."""
    monkeypatch.setattr("executionkit.claude_sdk._SDK_AVAILABLE", False)
    with pytest.raises(ImportError, match=r"executionkit\[claude\]"):
        ClaudeAgentProvider()


def test_is_not_a_tool_calling_provider() -> None:
    """react_loop() must reject this transport up front, not mid-loop."""
    provider = ClaudeAgentProvider()
    assert not isinstance(provider, ToolCallingProvider)
    assert _provider_supports_tools(provider) is False


# ---------------------------------------------------------------------------
# Message translation
# ---------------------------------------------------------------------------


def test_split_messages_single_user_turn_is_verbatim() -> None:
    system, prompt = _split_messages([{"role": "user", "content": "just this"}])
    assert system is None
    assert prompt == "just this"


def test_split_messages_hoists_system_turns() -> None:
    system, prompt = _split_messages(
        [
            {"role": "system", "content": "be terse"},
            {"role": "system", "content": "and kind"},
            {"role": "user", "content": "hello"},
        ]
    )
    assert system == "be terse\n\nand kind"
    assert prompt == "hello"


def test_split_messages_renders_multi_turn_transcript() -> None:
    system, prompt = _split_messages(
        [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
    )
    assert system is None
    assert prompt == "Human: first\n\nAssistant: reply\n\nHuman: second"


def test_split_messages_tolerates_missing_content() -> None:
    system, prompt = _split_messages([{"role": "user"}])
    assert system is None
    assert prompt == ""


async def test_constructor_system_prompt_precedes_message_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = patch_query(monkeypatch, assistant("ok"), result())
    provider = ClaudeAgentProvider(system_prompt="outer")
    await provider.complete(
        [{"role": "system", "content": "inner"}, {"role": "user", "content": "go"}]
    )
    assert fake.calls[0]["options"].system_prompt == "outer\n\ninner"


async def test_tools_are_disabled_on_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No filesystem, shell, or network side effects from a completion."""
    fake = patch_query(monkeypatch, assistant("ok"), result())
    await ClaudeAgentProvider().complete(USER)
    options = fake.calls[0]["options"]
    assert options.tools == []
    assert options.allowed_tools == []
    assert options.max_turns == 1


async def test_harness_knobs_are_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = patch_query(monkeypatch, assistant("ok"), result())
    provider = ClaudeAgentProvider(
        model="claude-sonnet-5",
        effort="low",
        thinking={"type": "adaptive"},
        max_budget_usd=0.5,
    )
    await provider.complete(USER)
    options = fake.calls[0]["options"]
    assert options.model == "claude-sonnet-5"
    assert options.effort == "low"
    assert options.thinking == {"type": "adaptive"}
    assert options.max_budget_usd == 0.5


# ---------------------------------------------------------------------------
# Unsupported knobs
# ---------------------------------------------------------------------------


async def test_temperature_warns_rather_than_silently_dropping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_query(monkeypatch, assistant("ok"), result())
    with pytest.warns(UserWarning, match="temperature"):
        await ClaudeAgentProvider().complete(USER, temperature=0.9)


async def test_max_tokens_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_query(monkeypatch, assistant("ok"), result())
    with pytest.warns(UserWarning, match="max_tokens"):
        await ClaudeAgentProvider().complete(USER, max_tokens=100)


async def test_tool_schemas_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_query(monkeypatch, assistant("ok"), result())
    with pytest.raises(PermanentError, match="tool schemas"):
        await ClaudeAgentProvider().complete(
            USER, tools=[{"type": "function", "function": {"name": "f"}}]
        )


def test_empty_tool_sequence_is_not_a_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty list means 'no tools', which this transport can honour."""
    ClaudeAgentProvider()._check_unsupported(None, None, [])


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


async def test_complete_concatenates_text_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_query(monkeypatch, assistant("Hello, "), assistant("world"), result())
    response = await ClaudeAgentProvider().complete(USER)
    assert response.content == "Hello, world"
    assert response.finish_reason == "end_turn"


async def test_complete_maps_anthropic_usage_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_query(
        monkeypatch,
        assistant("hi"),
        result(usage={"input_tokens": 11, "output_tokens": 3}, cost=0.25),
    )
    response = await ClaudeAgentProvider().complete(USER)
    assert response.input_tokens == 11
    assert response.output_tokens == 3
    assert response.total_tokens == 14
    assert response.usage["total_cost_usd"] == 0.25


async def test_complete_without_result_message_is_still_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_query(monkeypatch, assistant("orphan"))
    response = await ClaudeAgentProvider().complete(USER)
    assert response.content == "orphan"
    assert response.finish_reason == "stop"
    assert response.total_tokens == 0


async def test_complete_defaults_finish_reason_when_stop_reason_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_query(monkeypatch, assistant("x"), result(stop_reason=None))
    response = await ClaudeAgentProvider().complete(USER)
    assert response.finish_reason == "stop"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_rejected_rate_limit_raises_with_real_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resets_at = int(time.time()) + 300
    patch_query(monkeypatch, rate_limit("rejected", resets_at))
    with pytest.raises(RateLimitError) as excinfo:
        await ClaudeAgentProvider().complete(USER)
    assert 1.0 < excinfo.value.retry_after <= 300.0


async def test_allowed_warning_rate_limit_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_query(monkeypatch, rate_limit("allowed_warning"), assistant("ok"), result())
    response = await ClaudeAgentProvider().complete(USER)
    assert response.content == "ok"


def test_retry_after_falls_back_without_reset_timestamp() -> None:
    assert _retry_after_from(None) == 60.0


def test_retry_after_is_floored_for_a_past_reset() -> None:
    assert _retry_after_from(int(time.time()) - 10_000) == 1.0


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("authentication_failed", PermanentError),
        ("billing_error", PermanentError),
        ("invalid_request", PermanentError),
        ("rate_limit", RateLimitError),
        ("server_error", ProviderError),
        ("unknown", ProviderError),
    ],
)
async def test_assistant_errors_map_to_the_error_tree(
    monkeypatch: pytest.MonkeyPatch, error: str, expected: type[Exception]
) -> None:
    patch_query(monkeypatch, assistant("", error=error))
    with pytest.raises(expected):
        await ClaudeAgentProvider().complete(USER)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, RateLimitError),
        (400, PermanentError),
        (404, PermanentError),
        (500, ProviderError),
        (None, ProviderError),
    ],
)
async def test_failed_results_map_by_http_status(
    monkeypatch: pytest.MonkeyPatch, status: int | None, expected: type[Exception]
) -> None:
    patch_query(
        monkeypatch,
        result(is_error=True, api_error_status=status, errors=["boom"]),
    )
    with pytest.raises(expected, match="boom"):
        await ClaudeAgentProvider().complete(USER)


async def test_failed_result_without_errors_falls_back_to_subtype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_query(monkeypatch, result(is_error=True))
    with pytest.raises(ProviderError, match="success"):
        await ClaudeAgentProvider().complete(USER)


async def test_missing_cli_becomes_a_permanent_error_with_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from claude_agent_sdk import CLINotFoundError

    async def _boom(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        raise CLINotFoundError("nope")
        yield  # pragma: no cover - unreachable, makes this an async generator

    monkeypatch.setattr("executionkit.claude_sdk.query", _boom)
    with pytest.raises(PermanentError, match="subscription"):
        await ClaudeAgentProvider().complete(USER)


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------


async def test_stream_yields_text_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_query(monkeypatch, delta("Hel"), delta("lo"), assistant("Hello"), result())
    chunks = [chunk async for chunk in ClaudeAgentProvider().stream(USER)]
    assert chunks == ["Hel", "lo"]


async def test_stream_requests_partial_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = patch_query(monkeypatch, delta("x"), result())
    async for _ in ClaudeAgentProvider().stream(USER):
        pass
    assert fake.calls[0]["options"].include_partial_messages is True


async def test_stream_populates_usage_sink(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_query(
        monkeypatch,
        delta("a"),
        delta("b"),
        result(usage={"input_tokens": 5, "output_tokens": 2}, cost=0.01),
    )
    sink: list[Any] = []
    async for _ in ClaudeAgentProvider().stream(USER, usage_sink=sink):
        pass
    assert len(sink) == 1
    assert sink[0].content == "ab"
    assert sink[0].input_tokens == 5
    assert sink[0].output_tokens == 2


async def test_stream_propagates_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_query(monkeypatch, delta("a"), result(is_error=True, api_error_status=429))
    with pytest.raises(RateLimitError):
        async for _ in ClaudeAgentProvider().stream(USER):
            pass


async def test_stream_rejects_tool_schemas_before_iterating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard runs in stream(), not the generator, so it raises eagerly."""
    patch_query(monkeypatch, result())
    with pytest.raises(PermanentError, match="tool schemas"):
        ClaudeAgentProvider().stream(USER, tools=[{"name": "f"}])


@pytest.mark.parametrize(
    "event",
    [
        {"type": "message_start"},
        {"type": "content_block_delta", "delta": {"type": "thinking_delta"}},
        {"type": "content_block_delta", "delta": "not-a-dict"},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": None}},
    ],
)
def test_non_text_stream_events_yield_nothing(event: dict[str, Any]) -> None:
    assert _text_delta(StreamEvent(uuid="u", session_id="s", event=event)) == ""
