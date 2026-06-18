"""Tests for streaming support.

Covers the SSE parse helpers, the ``Provider`` urllib streaming transport
(httpx transport needs a live server and is ``# pragma: no cover``), the
``MockProvider`` stream, the ``checked_stream`` primitive, the ``Kit`` streaming
methods, and the ``stream=True`` guards on aggregating patterns.
"""

from __future__ import annotations

import email.message
import io
import logging
import unittest.mock
import urllib.error
from typing import TYPE_CHECKING, Any

import pytest

from executionkit import (
    DEFAULT_RETRY,
    BudgetExhaustedError,
    CostTracker,
    Kit,
    MockProvider,
    ProviderError,
    RateLimitError,
    StreamingPatternResult,
    TokenUsage,
    checked_stream,
    map_reduce,
    structured,
)
from executionkit.engine.messages import user_message
from executionkit.provider import (
    LLMResponse,
    Provider,
    _extract_stream_delta,
    _parse_sse_line,
    _response_from_usage_chunk,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _drain(stream: AsyncIterator[str]) -> list[str]:
    """Collect every chunk emitted by an async iterator."""
    return [chunk async for chunk in stream]


class _MidStreamFailProvider:
    """Streaming provider that yields a few chunks, then raises mid-stream."""

    def __init__(self, chunks: str, error: Exception) -> None:
        self._chunks = chunks
        self._error = error

    def stream(
        self, messages: Any, *, usage_sink: Any = None, **kwargs: Any
    ) -> AsyncIterator[str]:
        chunks = self._chunks
        error = self._error

        async def _gen() -> AsyncIterator[str]:
            for char in chunks:
                yield char
            raise error

        return _gen()


class _FakeHTTPResponse:
    """Minimal urllib response: a context manager that iterates byte lines."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def __iter__(self) -> Any:
        return iter(self._lines)


# ---------------------------------------------------------------------------
# SSE parse helpers
# ---------------------------------------------------------------------------


def test_parse_sse_line_decodes_data_object() -> None:
    assert _parse_sse_line('data: {"a": 1}') == {"a": 1}


def test_parse_sse_line_skips_done_blanks_and_non_data() -> None:
    assert _parse_sse_line("data: [DONE]") is None
    assert _parse_sse_line("") is None
    assert _parse_sse_line(": keep-alive comment") is None
    assert _parse_sse_line("event: ping") is None


def test_parse_sse_line_rejects_non_json_payload() -> None:
    with pytest.raises(ProviderError):
        _parse_sse_line("data: not-json{")


def test_extract_stream_delta() -> None:
    assert _extract_stream_delta({"choices": [{"delta": {"content": "hi"}}]}) == "hi"
    assert _extract_stream_delta({"choices": []}) is None
    assert _extract_stream_delta({"choices": [{"delta": {}}]}) is None


def test_response_from_usage_chunk() -> None:
    chunk = {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 2}}
    response = _response_from_usage_chunk(chunk, "hello")
    assert response is not None
    assert response.content == "hello"
    assert response.input_tokens == 1
    assert response.output_tokens == 2
    assert _response_from_usage_chunk({"choices": []}, "x") is None


# ---------------------------------------------------------------------------
# Provider urllib streaming transport
# ---------------------------------------------------------------------------


def _urllib_provider() -> Provider:
    """A Provider forced onto the stdlib urllib streaming path."""
    provider = Provider(base_url="http://localhost:1234/v1", model="m")
    object.__setattr__(provider, "_use_httpx", False)
    return provider


async def test_provider_stream_urllib_yields_deltas_and_records_usage() -> None:
    provider = _urllib_provider()
    lines = [
        b'data: {"choices":[{"delta":{"content":"He"}}]}\n',
        b'data: {"choices":[{"delta":{"content":"llo"}}]}\n',
        b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n',
        b"data: [DONE]\n",
    ]
    sink: list[LLMResponse] = []
    with unittest.mock.patch(
        "urllib.request.urlopen", return_value=_FakeHTTPResponse(lines)
    ):
        chunks = await _drain(provider.stream([user_message("hi")], usage_sink=sink))
    assert chunks == ["He", "llo"]
    assert sink[-1].input_tokens == 3
    assert sink[-1].output_tokens == 2
    await provider.aclose()


async def test_provider_stream_urllib_classifies_http_error() -> None:
    provider = _urllib_provider()
    http_error = urllib.error.HTTPError(
        "http://localhost:1234/v1/chat/completions",
        429,
        "Too Many Requests",
        email.message.Message(),
        io.BytesIO(b'{"error":{"message":"slow down"}}'),
    )
    with (
        unittest.mock.patch("urllib.request.urlopen", side_effect=http_error),
        pytest.raises(RateLimitError),
    ):
        await _drain(provider.stream([user_message("hi")]))
    await provider.aclose()


# ---------------------------------------------------------------------------
# MockProvider streaming
# ---------------------------------------------------------------------------


async def test_mock_provider_stream_yields_all_characters() -> None:
    provider = MockProvider(responses=["héllo"])
    chunks = await _drain(provider.stream([user_message("x")]))
    assert chunks == list("héllo")


async def test_mock_provider_stream_synthesizes_usage() -> None:
    provider = MockProvider(responses=["one two three"])
    sink: list[LLMResponse] = []
    await _drain(provider.stream([user_message("x")], usage_sink=sink))
    assert sink[-1].output_tokens == 3  # one whitespace-delimited token per word


# ---------------------------------------------------------------------------
# checked_stream
# ---------------------------------------------------------------------------


async def test_token_usage_available_after_drain() -> None:
    provider = MockProvider(responses=["hello world from the stream"])
    tracker = CostTracker()
    result = await checked_stream(provider, [user_message("x")], tracker, None, None)
    assert isinstance(result, StreamingPatternResult)
    await _drain(result.text_stream)
    assert result.cost.output_tokens > 0
    assert result.cost.llm_calls == 1


async def test_stream_budget_enforced_before_first_token() -> None:
    # In ExecutionKit a budget field of 0 means "unlimited", so exhaustion is
    # modelled with a tracker already at the call limit rather than budget=0.
    provider = MockProvider(responses=["hello"])
    tracker = CostTracker()
    tracker.reserve_call()  # tracker now reports 1 call
    budget = TokenUsage(llm_calls=1)  # already at the call limit
    with pytest.raises(BudgetExhaustedError):
        await checked_stream(provider, [user_message("x")], tracker, budget, None)
    assert provider.call_count == 0  # provider.stream() never invoked


async def test_stream_call_count_incremented_before_await() -> None:
    provider = MockProvider(responses=["hello"])
    tracker = CostTracker()
    result = await checked_stream(provider, [user_message("x")], tracker, None, None)
    # reserve_call() ran eagerly inside checked_stream, before any token is
    # awaited from the provider stream.
    assert tracker.call_count == 1
    # Token usage is only recorded after the stream drains.
    assert tracker.to_usage().output_tokens == 0
    await _drain(result.text_stream)
    assert tracker.to_usage().output_tokens > 0


async def test_stream_trace_events_fire_correctly() -> None:
    provider = MockProvider(responses=["hi"])
    tracker = CostTracker()
    events: list[str] = []

    async def trace(event: Any) -> None:
        events.append(event.kind)

    result = await checked_stream(
        provider, [user_message("x")], tracker, None, None, trace
    )
    assert events == ["llm_call_start"]  # fired before any token is yielded
    await _drain(result.text_stream)
    assert events == ["llm_call_start", "llm_call_end"]


async def test_stream_error_mid_stream_raises_provider_error() -> None:
    provider = _MidStreamFailProvider("abc", ProviderError("boom"))
    tracker = CostTracker()
    events: list[str] = []

    async def trace(event: Any) -> None:
        events.append(event.kind)

    result = await checked_stream(
        provider, [user_message("x")], tracker, None, None, trace
    )
    collected: list[str] = []
    with pytest.raises(ProviderError):
        async for chunk in result.text_stream:
            collected.append(chunk)
    assert collected == ["a", "b", "c"]
    assert events == ["llm_call_start", "llm_call_error"]


async def test_stream_retry_config_ignored_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = MockProvider(responses=["hello"])
    tracker = CostTracker()
    with caplog.at_level(logging.WARNING):
        result = await checked_stream(
            provider, [user_message("x")], tracker, None, DEFAULT_RETRY
        )
        await _drain(result.text_stream)
    assert any("retry is not supported" in r.getMessage() for r in caplog.records)
    assert provider.call_count == 1  # single attempt, no retry


# ---------------------------------------------------------------------------
# Aggregating patterns reject stream=True
# ---------------------------------------------------------------------------


async def test_structured_raises_on_stream_true() -> None:
    provider = MockProvider(responses=['{"x": 1}'])
    with pytest.raises(ValueError, match="stream=True is not supported"):
        await structured(provider, "p", stream=True)


async def test_map_reduce_raises_on_stream_true() -> None:
    provider = MockProvider(responses=["x"])
    with pytest.raises(ValueError, match="stream=True is not supported"):
        await map_reduce(
            provider,
            ["a"],
            map_prompt_template="{item}",
            reduce_prompt_template="{mapped_outputs}",
            stream=True,
        )


# ---------------------------------------------------------------------------
# Kit streaming methods
# ---------------------------------------------------------------------------


async def test_kit_stream_react_loop_returns_streaming_result() -> None:
    kit = Kit(MockProvider(responses=["streamed answer"]))
    result = await kit.stream_react_loop("question")
    assert isinstance(result, StreamingPatternResult)
    chunks = await _drain(result.text_stream)
    assert "".join(chunks) == "streamed answer"
    assert kit.usage.llm_calls == 1  # folded into Kit usage on drain


async def test_kit_stream_consensus_returns_streaming_result() -> None:
    kit = Kit(MockProvider(responses=["voted answer"]))
    result = await kit.stream_consensus("question")
    chunks = await _drain(result.text_stream)
    assert "".join(chunks) == "voted answer"
    assert result.cost.output_tokens > 0


async def test_kit_stream_rejects_non_streaming_provider() -> None:
    class _Blocking:
        async def complete(self, messages: Any, **kwargs: Any) -> LLMResponse:
            return LLMResponse(content="")

    kit = Kit(_Blocking())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="StreamingProvider"):
        await kit.stream_consensus("question")
