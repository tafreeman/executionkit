"""Tests for streaming support.

Covers the SSE parse helpers, the ``Provider`` urllib and httpx streaming
transports (the httpx transport is exercised end-to-end against an
``httpx.MockTransport`` — no live server required, see Finding EK#2), the
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
# Provider httpx streaming transport (SSE) — Finding EK#2
#
# httpx is the DEFAULT active transport whenever it is importable (including
# in this repo's own CI, since it is a `dev` extra installed alongside
# pytest/mypy/ruff), so `_stream_httpx` is live code, not a live-server-only
# path. These tests exercise it end-to-end via `httpx.MockTransport` — no
# network or live server required.
#
# RESOLVED (was flagged as two OPEN QUESTIONs; a verified research pass
# against httpx's own test suite / httpx-sse fixtures resolved both):
#
# 1. The 429/5xx tests below correctly exercise a *status-level* error
#    (detected when the streaming response's headers arrive, before any SSE
#    line is read) — a server cannot swap its status code after it starts
#    sending a 200 body, so there is no code path where good SSE chunks are
#    yielded and *then* an error status arrives.
# 2. Connections DO drop mid-body, though — that is a transport-level
#    ``httpx.ReadError`` raised while *iterating an already-200 body*, not a
#    status-code change. `test_provider_stream_httpx_read_error_raises_...`
#    below pins that case: a custom ``httpx.AsyncByteStream`` (the
#    httpx-sse/httpx test-suite fixture pattern — see
#    ``test_cancellation_during_stream`` in httpx's own tests) yields one good
#    chunk then raises ``httpx.ReadError`` from inside ``__aiter__``. Verified
#    against the installed httpx source that ``ReadError`` subclasses
#    ``TransportError``, so `_stream_httpx`'s existing
#    ``except _httpx.TransportError`` clause catches it and re-raises
#    ``ProviderError`` — no silent-truncation bug was found, so the test pins
#    passing (not xfail'd) behavior.
#
# `test_provider_stream_httpx_reassembles_event_split_across_chunk` below
# resolves the other flagged limitation (the materialized-body tests could not
# exercise TCP-level chunk-boundary splitting of a single ``data:`` line): it
# builds a real chunked stream via a custom ``httpx.AsyncByteStream`` (verified
# against installed httpx source: ``_decoders.py::LineDecoder`` buffers a
# split line across ``ByteChunker``/``TextChunker`` pass-through calls and
# reassembles it once the terminator arrives), so `_stream_httpx`'s line
# buffering across real chunk boundaries is now exercised, not assumed.
# ---------------------------------------------------------------------------


def _httpx_stream_provider(handler: Any) -> Provider:
    """A Provider forced onto the httpx SSE streaming transport, answered by
    an ``httpx.MockTransport`` running *handler* for every request.
    """
    import httpx

    provider = Provider(base_url="http://localhost:1234/v1", model="m")
    object.__setattr__(provider, "_use_httpx", True)
    object.__setattr__(
        provider,
        "_client",
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return provider


async def test_provider_stream_httpx_yields_deltas_and_records_usage() -> None:
    """Successful end-to-end SSE stream over the httpx transport."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    sse_body = (
        b'data: {"choices":[{"delta":{"content":"He"}}]}\n'
        b'data: {"choices":[{"delta":{"content":"llo"}}]}\n'
        b'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}\n'
        b"data: [DONE]\n"
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body)

    provider = _httpx_stream_provider(_handler)
    sink: list[LLMResponse] = []
    chunks = await _drain(provider.stream([user_message("hi")], usage_sink=sink))

    assert chunks == ["He", "llo"]
    assert sink[-1].input_tokens == 3
    assert sink[-1].output_tokens == 2
    await provider.aclose()


async def test_provider_stream_httpx_429_raises_rate_limit_error() -> None:
    """A 429 status on the SSE response classifies as RateLimitError."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "3"},
            json={"error": {"message": "slow down"}},
        )

    provider = _httpx_stream_provider(_handler)
    with pytest.raises(RateLimitError) as exc_info:
        await _drain(provider.stream([user_message("hi")]))
    assert exc_info.value.retry_after == 3.0
    await provider.aclose()


async def test_provider_stream_httpx_500_raises_provider_error() -> None:
    """A 5xx status on the SSE response classifies as ProviderError."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    provider = _httpx_stream_provider(_handler)
    with pytest.raises(ProviderError, match="boom"):
        await _drain(provider.stream([user_message("hi")]))
    await provider.aclose()


async def test_provider_stream_httpx_transport_error_raises_provider_error() -> None:
    """A transport-level failure opening the SSE stream is redacted and
    re-raised as ProviderError (not left as a raw httpx exception)."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = _httpx_stream_provider(_handler)
    with pytest.raises(ProviderError, match="Transport failure"):
        await _drain(provider.stream([user_message("hi")]))
    await provider.aclose()


async def test_provider_stream_httpx_reassembles_event_split_across_chunk() -> None:
    """A single SSE ``data:`` line delivered across two network-level byte
    chunks (the classic SSE client bug) must still parse into exactly one
    complete delta.

    Follow-up to the chunk-boundary OPEN QUESTION above: verified against the
    installed httpx 0.28.1 source (``_decoders.py::LineDecoder``,
    ``_client.py::BoundAsyncStream``) — a custom ``httpx.AsyncByteStream``
    (the httpx-sse fixture pattern) yields raw chunks unmerged all the way
    through ``aiter_raw`` -> ``aiter_bytes`` (``ByteChunker`` is a pass-through
    at the default ``chunk_size=None``) -> ``aiter_text`` -> ``aiter_lines``;
    ``LineDecoder.decode()`` buffers an incomplete line across calls and
    reassembles it once the terminating ``\\n`` arrives in a later chunk. This
    test pins that ``_stream_httpx`` correctly relies on that reassembly.
    """
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    class _ChunkedSSEBody(httpx.AsyncByteStream):
        """Yields raw bytes as separate, unmerged network-style chunks."""

        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = chunks

        async def __aiter__(self) -> AsyncIterator[bytes]:
            for chunk in self._chunks:
                yield chunk

    # The "data: ..." line is split mid-JSON across two chunks — exactly the
    # shape a TCP read can produce on a real connection.
    split_chunks = [
        b'data: {"choices": [{"delta"',
        b': {"content": "hello"}}]}\n',
        b'data: {"choices": [], "usage": '
        b'{"prompt_tokens": 1, "completion_tokens": 1}}\n',
        b"data: [DONE]\n",
    ]

    def _handler(request: httpx.Request) -> httpx.Response:
        # Fresh Response/body per call — an AsyncByteStream generator is
        # one-shot and would raise StreamConsumed if the transport retried.
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_ChunkedSSEBody(split_chunks),
        )

    provider = _httpx_stream_provider(_handler)
    sink: list[LLMResponse] = []
    chunks = await _drain(provider.stream([user_message("hi")], usage_sink=sink))

    # The split line must reassemble into exactly one complete delta — not
    # two malformed fragments and not a JSON parse error.
    assert chunks == ["hello"]
    assert sink[-1].input_tokens == 1
    assert sink[-1].output_tokens == 1
    await provider.aclose()


async def test_provider_stream_httpx_read_error_raises_provider_error() -> None:
    """A connection drop mid-body — after some good SSE lines were already
    delivered — must surface as ProviderError, not hang or silently truncate.

    Mirrors httpx's own ``test_cancellation_during_stream`` pattern: the
    ``AsyncByteStream`` yields one good chunk, then raises ``httpx.ReadError``
    from inside ``__aiter__`` to simulate a reset connection. Verified against
    the installed httpx source: ``ReadError`` subclasses ``NetworkError`` ->
    ``TransportError`` (``_exceptions.py``), so it is caught by
    ``_stream_httpx``'s existing ``except _httpx.TransportError`` clause —
    this pins that EK's intended contract is "surface the failure", not
    truncate silently; no truncation bug was found, so no xfail is needed.
    """
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    class _DroppedConnectionBody(httpx.AsyncByteStream):
        """Yields one good SSE line, then raises as if the connection reset."""

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"delta":{"content":"He"}}]}\n'
            raise httpx.ReadError("connection reset")

    def _handler(request: httpx.Request) -> httpx.Response:
        # Fresh Response/body per call — the generator body is one-shot.
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_DroppedConnectionBody(),
        )

    provider = _httpx_stream_provider(_handler)
    collected: list[str] = []
    with pytest.raises(ProviderError, match="Transport failure"):
        async for chunk in provider.stream([user_message("hi")]):
            collected.append(chunk)

    # The good delta delivered before the drop must not be hidden — the
    # failure is surfaced, not swallowed into a silently-truncated stream.
    assert collected == ["He"]
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
