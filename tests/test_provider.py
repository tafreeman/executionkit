"""Tests for provider.py — error hierarchy, value types, and Provider class."""

from __future__ import annotations

import http.client
import io
import unittest.mock
from dataclasses import FrozenInstanceError
from types import MappingProxyType
from urllib import error

import pytest

from executionkit.provider import (
    BudgetExhaustedError,
    ConsensusFailedError,
    ExecutionKitError,
    LLMError,
    LLMProvider,
    LLMResponse,
    MaxIterationsError,
    PatternError,
    PermanentError,
    Provider,
    ProviderError,
    RateLimitError,
    ToolCall,
)

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    """All 9 error classes exist with correct inheritance."""

    def test_execution_kit_error_is_exception(self) -> None:
        assert issubclass(ExecutionKitError, Exception)

    def test_llm_error_inherits_execution_kit_error(self) -> None:
        assert issubclass(LLMError, ExecutionKitError)

    def test_rate_limit_error_inherits_llm_error(self) -> None:
        assert issubclass(RateLimitError, LLMError)

    def test_permanent_error_inherits_llm_error(self) -> None:
        assert issubclass(PermanentError, LLMError)

    def test_provider_error_inherits_llm_error(self) -> None:
        assert issubclass(ProviderError, LLMError)

    def test_pattern_error_inherits_execution_kit_error(self) -> None:
        assert issubclass(PatternError, ExecutionKitError)

    def test_budget_exhausted_error_inherits_pattern_error(self) -> None:
        assert issubclass(BudgetExhaustedError, PatternError)

    def test_consensus_failed_error_inherits_pattern_error(self) -> None:
        assert issubclass(ConsensusFailedError, PatternError)

    def test_max_iterations_error_inherits_pattern_error(self) -> None:
        assert issubclass(MaxIterationsError, PatternError)

    def test_rate_limit_error_has_retry_after_attribute(self) -> None:
        err = RateLimitError("limited", retry_after=5.0)
        assert err.retry_after == 5.0

    def test_rate_limit_error_default_retry_after(self) -> None:
        err = RateLimitError("limited")
        assert err.retry_after == 1.0

    def test_rate_limit_error_message(self) -> None:
        err = RateLimitError("rate limited")
        assert str(err) == "rate limited"

    def test_permanent_error_not_retryable_by_design(self) -> None:
        # PermanentError must NOT be a subclass of RateLimitError or ProviderError
        assert not issubclass(PermanentError, RateLimitError)
        assert not issubclass(PermanentError, ProviderError)

    def test_all_llm_errors_inherit_execution_kit_error(self) -> None:
        for cls in (RateLimitError, PermanentError, ProviderError):
            assert issubclass(cls, ExecutionKitError)

    def test_all_pattern_errors_inherit_execution_kit_error(self) -> None:
        for cls in (BudgetExhaustedError, ConsensusFailedError, MaxIterationsError):
            assert issubclass(cls, ExecutionKitError)

    def test_can_catch_llm_errors_by_base(self) -> None:
        with pytest.raises(LLMError):
            raise RateLimitError("oops")

    def test_can_catch_pattern_errors_by_base(self) -> None:
        with pytest.raises(PatternError):
            raise BudgetExhaustedError("over budget")

    def test_can_catch_all_errors_by_execution_kit_error(self) -> None:
        for exc_class in (
            LLMError,
            RateLimitError,
            PermanentError,
            ProviderError,
            PatternError,
            BudgetExhaustedError,
            ConsensusFailedError,
            MaxIterationsError,
        ):
            with pytest.raises(ExecutionKitError):
                raise exc_class("test")


# ---------------------------------------------------------------------------
# ToolCall
# ---------------------------------------------------------------------------


class TestToolCall:
    def test_toolcall_is_frozen(self) -> None:
        tc = ToolCall(id="tc1", name="search", arguments={"query": "hello"})
        with pytest.raises(AttributeError):
            tc.name = "other"  # type: ignore[misc]

    def test_toolcall_fields(self) -> None:
        tc = ToolCall(id="abc", name="calculator", arguments={"x": 1, "y": 2})
        assert tc.id == "abc"
        assert tc.name == "calculator"
        assert tc.arguments == {"x": 1, "y": 2}

    def test_toolcall_empty_arguments(self) -> None:
        tc = ToolCall(id="", name="noop", arguments={})
        assert tc.arguments == {}

    def test_toolcall_equality(self) -> None:
        tc1 = ToolCall(id="x", name="fn", arguments={"a": 1})
        tc2 = ToolCall(id="x", name="fn", arguments={"a": 1})
        assert tc1 == tc2

    def test_toolcall_inequality(self) -> None:
        tc1 = ToolCall(id="x", name="fn", arguments={"a": 1})
        tc2 = ToolCall(id="y", name="fn", arguments={"a": 1})
        assert tc1 != tc2


# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_llmresponse_is_frozen(self) -> None:
        r = LLMResponse(content="hello")
        with pytest.raises(AttributeError):
            r.content = "other"  # type: ignore[misc]

    def test_llmresponse_default_fields(self) -> None:
        r = LLMResponse(content="hi")
        assert r.content == "hi"
        assert r.tool_calls == ()
        assert r.finish_reason == "stop"
        assert r.usage == MappingProxyType({})
        assert r.raw is None

    def test_input_tokens_from_prompt_tokens(self) -> None:
        r = LLMResponse(content="", usage=MappingProxyType({"prompt_tokens": 42}))
        assert r.input_tokens == 42

    def test_input_tokens_from_input_tokens_key(self) -> None:
        r = LLMResponse(content="", usage=MappingProxyType({"input_tokens": 55}))
        assert r.input_tokens == 55

    def test_output_tokens_from_completion_tokens(self) -> None:
        r = LLMResponse(content="", usage=MappingProxyType({"completion_tokens": 10}))
        assert r.output_tokens == 10

    def test_output_tokens_from_output_tokens_key(self) -> None:
        r = LLMResponse(content="", usage=MappingProxyType({"output_tokens": 20}))
        assert r.output_tokens == 20

    def test_total_tokens(self) -> None:
        r = LLMResponse(
            content="",
            usage=MappingProxyType({"prompt_tokens": 30, "completion_tokens": 15}),
        )
        assert r.total_tokens == 45

    def test_total_tokens_zero_when_no_usage(self) -> None:
        r = LLMResponse(content="")
        assert r.total_tokens == 0

    def test_was_truncated_when_finish_reason_length(self) -> None:
        r = LLMResponse(content="truncated...", finish_reason="length")
        assert r.was_truncated is True

    def test_was_truncated_false_when_stop(self) -> None:
        r = LLMResponse(content="complete", finish_reason="stop")
        assert r.was_truncated is False

    def test_has_tool_calls_false_by_default(self) -> None:
        r = LLMResponse(content="text")
        assert r.has_tool_calls is False

    def test_has_tool_calls_true_with_tool_calls(self) -> None:
        tc = ToolCall(id="1", name="fn", arguments={})
        r = LLMResponse(content="", tool_calls=(tc,))
        assert r.has_tool_calls is True

    def test_input_tokens_zero_when_no_usage(self) -> None:
        r = LLMResponse(content="")
        assert r.input_tokens == 0

    def test_output_tokens_zero_when_no_usage(self) -> None:
        r = LLMResponse(content="")
        assert r.output_tokens == 0

    def test_dual_format_input_prefers_input_tokens(self) -> None:
        # When both keys present, input_tokens takes priority (truthy check)
        r = LLMResponse(
            content="",
            usage=MappingProxyType({"input_tokens": 5, "prompt_tokens": 99}),
        )
        assert r.input_tokens == 5


def test_dual_format_input_tokens_zero_not_falsy() -> None:
    # input_tokens=0 (e.g. cached prompt) must NOT fall back to prompt_tokens
    r = LLMResponse(
        content="",
        usage=MappingProxyType({"input_tokens": 0, "prompt_tokens": 99}),
    )
    assert r.input_tokens == 0


def test_usage_rejects_negative_token_counts() -> None:
    r = LLMResponse(content="", usage=MappingProxyType({"prompt_tokens": -1}))

    with pytest.raises(ProviderError, match="negative"):
        _ = r.input_tokens


def test_usage_rejects_non_integer_token_counts() -> None:
    r = LLMResponse(content="", usage=MappingProxyType({"completion_tokens": "many"}))

    with pytest.raises(ProviderError, match="integer"):
        _ = r.output_tokens


def test_usage_rejects_absurd_token_counts() -> None:
    r = LLMResponse(
        content="",
        usage=MappingProxyType({"input_tokens": 1_000_000_001}),
    )

    with pytest.raises(ProviderError, match="unreasonably large"):
        _ = r.input_tokens


# ---------------------------------------------------------------------------
# Provider constructor
# ---------------------------------------------------------------------------


class TestProvider:
    def test_provider_fields(self) -> None:
        p = Provider(base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        assert p.base_url == "https://api.openai.com/v1"
        assert p.model == "gpt-4o-mini"
        assert p.api_key == ""
        assert p.default_temperature == 0.7
        assert p.default_max_tokens == 4096
        assert p.timeout == 120.0

    def test_provider_custom_fields(self) -> None:
        p = Provider(
            base_url="http://localhost:11434/v1",
            model="llama3.2",
            api_key="sk-test",
            default_temperature=0.5,
            default_max_tokens=2048,
            timeout=30.0,
        )
        assert p.api_key == "sk-test"
        assert p.default_temperature == 0.5
        assert p.default_max_tokens == 2048
        assert p.timeout == 30.0

    def test_provider_satisfies_llm_provider_protocol(self) -> None:
        p = Provider(base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        assert isinstance(p, LLMProvider)

    def test_mock_provider_satisfies_llm_provider_protocol(self) -> None:
        from executionkit._mock import MockProvider

        mp = MockProvider(responses=["hi"])
        assert isinstance(mp, LLMProvider)

    def test_provider_repr_masks_api_key(self) -> None:
        p = Provider(base_url="http://x", model="gpt", api_key="sk-real-secret")
        assert "sk-real-secret" not in repr(p)

    def test_provider_repr_shows_masked_marker(self) -> None:
        p = Provider(base_url="http://x", model="gpt", api_key="sk-real-secret")
        assert "***" in repr(p)

    def test_provider_repr_empty_key_no_marker(self) -> None:
        p = Provider(base_url="http://x", model="gpt", api_key="")
        assert "***" not in repr(p)

    def test_provider_repr_contains_model_and_url(self) -> None:
        p = Provider(base_url="http://x", model="gpt", api_key="sk-real-secret")
        result = repr(p)
        assert "http://x" in result
        assert "gpt" in result


# ---------------------------------------------------------------------------
# MB-007a: was_truncated recognises "max_tokens" finish reason
# ---------------------------------------------------------------------------


def test_parse_response_was_truncated_on_max_tokens() -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    response = provider._parse_response(
        {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "max_tokens"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    assert response.was_truncated is True


# ---------------------------------------------------------------------------
# MB-007b: was_truncated is False for normal stop
# ---------------------------------------------------------------------------


def test_parse_response_was_truncated_false_on_stop() -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    response = provider._parse_response(
        {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    assert response.was_truncated is False


# ---------------------------------------------------------------------------
# MB-007c: ToolCallingProvider isinstance check passes for MockProvider
# ---------------------------------------------------------------------------


def test_mock_provider_satisfies_tool_calling_provider() -> None:
    from executionkit._mock import MockProvider
    from executionkit.provider import ToolCallingProvider

    mock = MockProvider(responses=["hello"])
    assert isinstance(mock, ToolCallingProvider)


# ---------------------------------------------------------------------------
# P1-7: 5xx maps to ProviderError
# ---------------------------------------------------------------------------


async def test_post_maps_5xx_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = Provider("https://example.com/v1", model="test-model")

    def fake_urlopen(*args: object, **kwargs: object) -> object:
        raise error.HTTPError(
            url="https://example.com/v1/chat/completions",
            code=500,
            msg="Internal Server Error",
            hdrs=http.client.HTTPMessage(),
            fp=io.BytesIO(b'{"error":{"message":"server error"}}'),
        )

    # Force urllib backend so the monkeypatch is effective regardless of
    # whether httpx is installed in the test environment.
    object.__setattr__(provider, "_use_httpx", False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderError, match="server error"):
        await provider._post("chat/completions", {"model": "x"})


# ---------------------------------------------------------------------------
# P1-7b: input_tokens=0 does not fall back to prompt_tokens
# ---------------------------------------------------------------------------


def test_parse_response_zero_input_tokens_not_falsy() -> None:
    """input_tokens=0 (cached prompt) must not fall back to prompt_tokens."""
    provider = Provider("https://example.com/v1", model="test-model")
    response = provider._parse_response(
        {
            "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
            "usage": {"input_tokens": 0, "prompt_tokens": 5, "completion_tokens": 2},
        }
    )
    assert response.input_tokens == 0
    assert response.output_tokens == 2


# ---------------------------------------------------------------------------
# P2-SEC-07: _format_http_error redacts key fragments
# ---------------------------------------------------------------------------


def test_format_http_error_redacts_key_fragment() -> None:
    """Raw provider error messages containing API key fragments must be redacted."""
    from executionkit.provider import _format_http_error

    payload = {"error": {"message": "key sk-abc123xyz invalid"}}
    result = _format_http_error(401, payload)

    assert "sk-abc123xyz" not in result
    assert "[REDACTED]" in result


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_1234567890abcdef",
        "gho_1234567890abcdef",
        "AIzaSyA1234567890abcdef",
        "xoxb-1234567890-abcdef",
        "xoxp-1234567890-abcdef",
        "xoxo-1234567890-abcdef",
        "xoxa-1234567890-abcdef",
        "gsk_1234567890abcdef",
        "bearer abcdef12345",
        "Bearer abcdef12345",
        "token abcdef12345",
    ],
)
def test_redact_sensitive_covers_common_key_shapes(secret: str) -> None:
    from executionkit.provider import _redact_sensitive

    redacted = _redact_sensitive(f"credential {secret} leaked")

    assert secret not in redacted
    assert "[REDACTED]" in redacted


# ---------------------------------------------------------------------------
# P1-5: httpx backend tests
# ---------------------------------------------------------------------------


def test_provider_uses_httpx_when_available() -> None:
    """Provider._use_httpx is True when httpx can be imported."""
    try:
        import httpx  # noqa: F401
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    assert provider._use_httpx is True
    assert provider._client is not None


def test_provider_falls_back_to_urllib(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider._use_httpx is False when httpx is unavailable."""
    import executionkit.provider as pmod

    monkeypatch.setattr(pmod, "_HTTPX_AVAILABLE", False)
    monkeypatch.setattr(pmod, "_httpx", None)

    provider = Provider("https://example.com/v1", model="test-model")
    assert provider._use_httpx is False
    assert provider._client is None


def test_same_client_reused_across_calls() -> None:
    """The httpx.AsyncClient instance is reused between calls (connection pool)."""
    try:
        import httpx  # noqa: F401
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    client_id_before = id(provider._client)
    # Simulate a second "call" — client must not be recreated
    client_id_after = id(provider._client)
    assert client_id_before == client_id_after


async def test_post_httpx_maps_429_to_rate_limit_error() -> None:
    """_post_httpx maps HTTP 429 to RateLimitError with retry_after."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {"retry-after": "3"}
    mock_response.json.return_value = {"error": "rate limited"}

    exc = httpx.HTTPStatusError(
        "429", request=unittest.mock.MagicMock(), response=mock_response
    )

    async def fake_post(*args: object, **kwargs: object) -> object:
        raise exc

    mock_client = unittest.mock.MagicMock()
    mock_client.post = fake_post
    object.__setattr__(provider, "_client", mock_client)

    with pytest.raises(RateLimitError) as exc_info:
        await provider._post_httpx("https://example.com/v1/chat/completions", b"{}", {})
    assert exc_info.value.retry_after == 3.0


async def test_post_httpx_maps_401_to_permanent_error() -> None:
    """_post_httpx maps HTTP 401 to PermanentError."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 401
    mock_response.headers = {}
    mock_response.json.return_value = {"error": {"message": "Unauthorized"}}

    exc = httpx.HTTPStatusError(
        "401", request=unittest.mock.MagicMock(), response=mock_response
    )

    async def fake_post(*args: object, **kwargs: object) -> object:
        raise exc

    mock_client = unittest.mock.MagicMock()
    mock_client.post = fake_post
    object.__setattr__(provider, "_client", mock_client)

    with pytest.raises(PermanentError):
        await provider._post_httpx("https://example.com/v1/chat/completions", b"{}", {})


async def test_post_httpx_maps_500_to_provider_error() -> None:
    """_post_httpx maps HTTP 5xx to ProviderError."""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 500
    mock_response.headers = {}
    mock_response.json.return_value = {"error": {"message": "internal error"}}

    exc = httpx.HTTPStatusError(
        "500", request=unittest.mock.MagicMock(), response=mock_response
    )

    async def fake_post(*args: object, **kwargs: object) -> object:
        raise exc

    mock_client = unittest.mock.MagicMock()
    mock_client.post = fake_post
    object.__setattr__(provider, "_client", mock_client)

    with pytest.raises(ProviderError, match="internal error"):
        await provider._post_httpx("https://example.com/v1/chat/completions", b"{}", {})


async def test_aclose_with_httpx() -> None:
    """aclose() calls client.aclose() when httpx is the active backend."""
    try:
        import httpx  # noqa: F401
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    closed: list[bool] = []

    async def fake_aclose() -> None:
        closed.append(True)

    mock_client = unittest.mock.MagicMock()
    mock_client.aclose = fake_aclose
    object.__setattr__(provider, "_client", mock_client)

    await provider.aclose()
    assert closed == [True]


async def test_aclose_noop_without_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """aclose() is a no-op when the urllib backend is active."""
    import executionkit.provider as pmod

    monkeypatch.setattr(pmod, "_HTTPX_AVAILABLE", False)
    monkeypatch.setattr(pmod, "_httpx", None)

    provider = Provider("https://example.com/v1", model="test-model")
    assert provider._use_httpx is False
    # Must not raise
    await provider.aclose()


async def test_context_manager_closes_client() -> None:
    """Using Provider as async context manager calls aclose() on exit."""
    try:
        import httpx  # noqa: F401
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    closed: list[bool] = []

    async def fake_aclose() -> None:
        closed.append(True)

    mock_client = unittest.mock.MagicMock()
    mock_client.aclose = fake_aclose
    object.__setattr__(provider, "_client", mock_client)

    async with provider:
        pass

    assert closed == [True]


# ---------------------------------------------------------------------------
# Provider immutability
# ---------------------------------------------------------------------------


class TestProviderImmutability:
    def test_provider_is_immutable(self) -> None:
        """Public field assignment on Provider must raise FrozenInstanceError."""
        provider = Provider("https://api.openai.com/v1", model="gpt-4o-mini")
        with pytest.raises(FrozenInstanceError):
            provider.model = "new"  # type: ignore[misc]

    def test_provider_client_is_set_post_init(self) -> None:
        """_use_httpx is set to a bool by __post_init__ regardless of httpx."""
        provider = Provider("https://api.openai.com/v1", model="gpt-4o-mini")
        assert isinstance(provider._use_httpx, bool)


# ---------------------------------------------------------------------------
# _classify_http_error regression tests (F-02)
# Ref: extracted to eliminate duplication between urllib and httpx backends.
# Anthropic SDK uses same pattern in _make_status_error().
# ---------------------------------------------------------------------------


class TestClassifyHttpError:
    """_classify_http_error maps HTTP status codes to the correct exception."""

    def test_429_raises_rate_limit_error(self) -> None:
        from executionkit.provider import _classify_http_error

        cause = Exception("original")
        with pytest.raises(RateLimitError) as exc_info:
            _classify_http_error(429, {}, 5.0, cause=cause)
        assert exc_info.value.retry_after == 5.0
        assert exc_info.value.__cause__ is cause

    def test_429_default_retry_after_is_propagated(self) -> None:
        from executionkit.provider import _classify_http_error

        with pytest.raises(RateLimitError) as exc_info:
            _classify_http_error(429, {}, 2.5, cause=Exception())
        assert exc_info.value.retry_after == 2.5

    def test_401_raises_permanent_error(self) -> None:
        from executionkit.provider import _classify_http_error

        with pytest.raises(PermanentError):
            _classify_http_error(401, {}, 1.0, cause=Exception())

    def test_403_raises_permanent_error(self) -> None:
        from executionkit.provider import _classify_http_error

        with pytest.raises(PermanentError):
            _classify_http_error(403, {}, 1.0, cause=Exception())

    def test_404_raises_permanent_error(self) -> None:
        from executionkit.provider import _classify_http_error

        with pytest.raises(PermanentError):
            _classify_http_error(404, {}, 1.0, cause=Exception())

    def test_500_raises_provider_error(self) -> None:
        from executionkit.provider import _classify_http_error

        with pytest.raises(ProviderError):
            _classify_http_error(500, {}, 1.0, cause=Exception())

    def test_503_raises_provider_error(self) -> None:
        from executionkit.provider import _classify_http_error

        with pytest.raises(ProviderError):
            _classify_http_error(503, {}, 1.0, cause=Exception())

    # FIX #1: non-retryable client errors must map to PermanentError
    @pytest.mark.parametrize("status", [400, 405, 413, 422])
    def test_non_retryable_4xx_raises_permanent_error(self, status: int) -> None:
        """HTTP 400/405/413/422 must raise PermanentError, not ProviderError."""
        from executionkit.provider import _classify_http_error

        with pytest.raises(PermanentError):
            _classify_http_error(status, {}, 1.0, cause=Exception())

    @pytest.mark.parametrize("status", [400, 405, 413, 422])
    def test_non_retryable_4xx_is_not_provider_error(self, status: int) -> None:
        """PermanentError must not be a ProviderError (would make it retryable)."""
        from executionkit.provider import _classify_http_error

        with pytest.raises(PermanentError) as exc_info:
            _classify_http_error(status, {}, 1.0, cause=Exception())
        assert not isinstance(exc_info.value, ProviderError)

    def test_409_raises_retryable_provider_error(self) -> None:
        """HTTP 409 (Conflict) must raise ProviderError (retryable), not PermanentError.

        OpenAI-compatible endpoints can return 409 for transient lock/conflict
        situations that official clients retry; keeping it as ProviderError
        ensures DEFAULT_RETRY handles it.
        """
        from executionkit.provider import _classify_http_error

        with pytest.raises(ProviderError) as exc_info:
            _classify_http_error(409, {}, 1.0, cause=Exception())
        assert not isinstance(exc_info.value, PermanentError)

    def test_exception_is_chained_via_cause(self) -> None:
        """raise ... from cause must set __cause__, not just __context__."""
        from executionkit.provider import _classify_http_error

        original = ValueError("root cause")
        with pytest.raises(ProviderError) as exc_info:
            _classify_http_error(500, {}, 1.0, cause=original)
        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# Targeted provider transport + parsing coverage
# ---------------------------------------------------------------------------


async def test_complete_builds_payload_with_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Provider(
        "https://example.com/v1",
        model="test-model",
        default_temperature=0.25,
        default_max_tokens=321,
    )
    captured: dict[str, object] = {}

    async def fake_post(
        self: Provider,
        endpoint: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }

    monkeypatch.setattr(Provider, "_post", fake_post)

    response = await provider.complete([{"role": "user", "content": "hi"}])

    assert response.content == "hello"
    assert captured["endpoint"] == "chat/completions"
    assert captured["payload"] == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.25,
        "max_tokens": 321,
    }


async def test_complete_includes_tools_and_extra_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    captured: dict[str, object] = {}
    tools = [{"type": "function", "function": {"name": "lookup"}}]

    async def fake_post(
        self: Provider,
        endpoint: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4},
        }

    monkeypatch.setattr(Provider, "_post", fake_post)

    response = await provider.complete(
        [{"role": "user", "content": "hi"}],
        temperature=0.9,
        max_tokens=12,
        tools=tools,
        top_p=0.8,
    )

    assert response.was_truncated is True
    assert captured["endpoint"] == "chat/completions"
    assert captured["payload"] == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.9,
        "max_tokens": 12,
        "tools": tools,
        "top_p": 0.8,
    }


async def test_post_routes_to_httpx_with_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Provider("https://example.com/v1/", model="test-model", api_key="abc123")
    object.__setattr__(provider, "_use_httpx", True)
    captured: dict[str, object] = {}

    async def fake_post_httpx(
        self: Provider,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, object]:
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        return {"ok": True}

    monkeypatch.setattr(Provider, "_post_httpx", fake_post_httpx)

    result = await provider._post("/chat/completions", {"x": 1})

    assert result == {"ok": True}
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["body"] == b'{"x": 1}'
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer abc123",
    }


async def test_post_routes_to_urllib_without_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    object.__setattr__(provider, "_use_httpx", False)
    captured: dict[str, object] = {}

    async def fake_post_urllib(
        self: Provider,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, object]:
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        return {"ok": True}

    monkeypatch.setattr(Provider, "_post_urllib", fake_post_urllib)

    result = await provider._post("chat/completions", {"x": 2})

    assert result == {"ok": True}
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["body"] == b'{"x": 2}'
    assert captured["headers"] == {"Content-Type": "application/json"}


async def test_post_httpx_success_returns_json_dict() -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    mock_response = unittest.mock.MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"choices": []}

    async def fake_post(*args: object, **kwargs: object) -> object:
        return mock_response

    mock_client = unittest.mock.MagicMock()
    mock_client.post = fake_post
    object.__setattr__(provider, "_client", mock_client)

    result = await provider._post_httpx(
        "https://example.com/v1/chat/completions",
        b"{}",
        {},
    )
    assert result == {"choices": []}


async def test_post_httpx_handles_non_dict_error_payload() -> None:
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 500
    mock_response.headers = {}
    mock_response.json.return_value = ["not", "a", "dict"]

    exc = httpx.HTTPStatusError(
        "500", request=unittest.mock.MagicMock(), response=mock_response
    )

    async def fake_post(*args: object, **kwargs: object) -> object:
        raise exc

    mock_client = unittest.mock.MagicMock()
    mock_client.post = fake_post
    object.__setattr__(provider, "_client", mock_client)

    with pytest.raises(ProviderError, match="HTTP 500"):
        await provider._post_httpx("https://example.com/v1/chat/completions", b"{}", {})


async def test_post_httpx_handles_json_parse_error_in_error_response() -> None:
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    mock_response = unittest.mock.MagicMock()
    mock_response.status_code = 500
    mock_response.headers = {}
    mock_response.json.side_effect = ValueError("bad json")

    exc = httpx.HTTPStatusError(
        "500", request=unittest.mock.MagicMock(), response=mock_response
    )

    async def fake_post(*args: object, **kwargs: object) -> object:
        raise exc

    mock_client = unittest.mock.MagicMock()
    mock_client.post = fake_post
    object.__setattr__(provider, "_client", mock_client)

    with pytest.raises(ProviderError, match="HTTP 500"):
        await provider._post_httpx("https://example.com/v1/chat/completions", b"{}", {})


async def test_post_httpx_maps_transport_error_to_provider_error() -> None:
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    provider = Provider("https://example.com/v1", model="test-model")
    if not provider._use_httpx:
        pytest.skip("httpx backend not active")

    async def fake_post(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("boom")

    mock_client = unittest.mock.MagicMock()
    mock_client.post = fake_post
    object.__setattr__(provider, "_client", mock_client)

    with pytest.raises(ProviderError, match="Transport failure: boom"):
        await provider._post_httpx("https://example.com/v1/chat/completions", b"{}", {})


async def test_post_urllib_success_returns_json_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    object.__setattr__(provider, "_use_httpx", False)

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"hi"}}]}'

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = await provider._post_urllib(
        "https://example.com/v1/chat/completions",
        b"{}",
        {},
    )
    assert result == {"choices": [{"message": {"content": "hi"}}]}


async def test_post_urllib_invalid_error_body_falls_back_to_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    object.__setattr__(provider, "_use_httpx", False)

    def fake_urlopen(*args: object, **kwargs: object) -> object:
        raise error.HTTPError(
            url="https://example.com/v1/chat/completions",
            code=500,
            msg="Internal Server Error",
            hdrs=http.client.HTTPMessage(),
            fp=io.BytesIO(b"not-json"),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderError, match="HTTP 500"):
        await provider._post_urllib(
            "https://example.com/v1/chat/completions",
            b"{}",
            {},
        )


async def test_post_urllib_maps_urlerror_to_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    object.__setattr__(provider, "_use_httpx", False)

    def fake_urlopen(*args: object, **kwargs: object) -> object:
        raise error.URLError("dns down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ProviderError, match="Transport failure: dns down"):
        await provider._post_urllib(
            "https://example.com/v1/chat/completions",
            b"{}",
            {},
        )


def test_parse_response_handles_non_dict_usage() -> None:
    provider = Provider("https://example.com/v1", model="test-model")
    response = provider._parse_response(
        {
            "choices": [{"message": {"content": "hello"}, "finish_reason": None}],
            "usage": ["not", "a", "dict"],
        }
    )
    assert response.content == "hello"
    assert response.finish_reason == "None"
    assert dict(response.usage) == {}


def test_first_choice_raises_when_missing_choices() -> None:
    from executionkit.provider import _first_choice

    with pytest.raises(ProviderError, match="did not include any choices"):
        _first_choice({})


def test_first_choice_raises_when_first_choice_not_object() -> None:
    from executionkit.provider import _first_choice

    with pytest.raises(ProviderError, match="was not an object"):
        _first_choice({"choices": ["bad"]})


def test_extract_content_handles_mixed_content_list() -> None:
    from executionkit.provider import _extract_content

    result = _extract_content(
        [
            "alpha",
            {"type": "text", "text": "beta"},
            {"type": "output_text", "text": {"value": "gamma"}},
            {"value": "delta"},
            123,
        ]
    )

    assert result == "alphabetagammadelta"


# ---------------------------------------------------------------------------
# FIX #1 acceptance test: HTTP 422 → one wire attempt, no backoff sleeps
# Asserts that a provider returning HTTP 422 raises PermanentError after a
# single complete() attempt.  Because PermanentError is not in the default
# RetryConfig.retryable tuple, the retry loop must not sleep or retry.
# ---------------------------------------------------------------------------


async def test_422_raises_permanent_error_after_single_attempt() -> None:
    """Provider returning HTTP 422 makes exactly one wire attempt (DEFAULT_RETRY)."""
    from executionkit.cost import CostTracker
    from executionkit.engine.retry import DEFAULT_RETRY
    from executionkit.patterns.base import checked_complete
    from executionkit.provider import PermanentError

    call_count = 0

    class Provider422:
        async def complete(self, messages: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            raise PermanentError("Provider request failed with HTTP 422")

    tracker = CostTracker()
    with pytest.raises(PermanentError):
        await checked_complete(
            Provider422(),  # type: ignore[arg-type]
            [{"role": "user", "content": "hi"}],
            tracker,
            budget=None,
            retry=DEFAULT_RETRY,
        )

    # PermanentError is not retryable — must stop after the first attempt.
    assert call_count == 1, f"Expected 1 attempt, got {call_count}"
    # reserve_call() is called once before the attempt
    assert tracker.call_count == 1, (
        f"Expected tracker.call_count==1, got {tracker.call_count}"
    )


async def test_500_retries_under_default_retry() -> None:
    """Provider returning HTTP 500 (ProviderError) retries under DEFAULT_RETRY."""
    from executionkit.cost import CostTracker
    from executionkit.engine.retry import RetryConfig
    from executionkit.patterns.base import checked_complete
    from executionkit.provider import ProviderError

    call_count = 0

    class Provider500:
        async def complete(self, messages: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            raise ProviderError("Provider request failed with HTTP 500")

    tracker = CostTracker()
    # Use a no-sleep retry config to keep the test fast
    fast_retry = RetryConfig(max_retries=3, base_delay=0.0)
    with pytest.raises(ProviderError):
        await checked_complete(
            Provider500(),  # type: ignore[arg-type]
            [{"role": "user", "content": "hi"}],
            tracker,
            budget=None,
            retry=fast_retry,
        )

    # ProviderError is retryable — must attempt max_retries times
    assert call_count == fast_retry.max_retries, (
        f"Expected {fast_retry.max_retries} attempts, got {call_count}"
    )


def test_extract_content_stringifies_non_list_non_string() -> None:
    from executionkit.provider import _extract_content

    assert _extract_content(42) == "42"


def test_parse_tool_calls_parses_missing_id_as_empty_string() -> None:
    from executionkit.provider import _parse_tool_calls

    result = _parse_tool_calls(
        [{"function": {"name": "lookup", "arguments": '{"q":"hi"}'}}]
    )

    assert result == [ToolCall(id="", name="lookup", arguments={"q": "hi"})]


def test_parse_tool_calls_raises_when_payload_not_list() -> None:
    from executionkit.provider import _parse_tool_calls

    with pytest.raises(ProviderError, match="payload was not a list"):
        _parse_tool_calls("bad")


def test_parse_tool_calls_raises_when_item_not_object() -> None:
    from executionkit.provider import _parse_tool_calls

    with pytest.raises(ProviderError, match="payload was not an object"):
        _parse_tool_calls(["bad"])


def test_parse_tool_calls_raises_when_function_not_object() -> None:
    from executionkit.provider import _parse_tool_calls

    with pytest.raises(ProviderError, match="function payload was not an object"):
        _parse_tool_calls([{"function": "bad"}])


def test_parse_tool_calls_raises_when_name_missing() -> None:
    from executionkit.provider import _parse_tool_calls

    with pytest.raises(ProviderError, match="name was missing"):
        _parse_tool_calls([{"function": {"arguments": "{}"}}])


def test_parse_tool_arguments_handles_none_and_dict() -> None:
    from executionkit.provider import _parse_tool_arguments

    assert _parse_tool_arguments(None) == {}
    assert _parse_tool_arguments({"x": 1}) == {"x": 1}


def test_parse_tool_arguments_raises_on_invalid_type() -> None:
    from executionkit.provider import _parse_tool_arguments

    with pytest.raises(ProviderError, match="dict or JSON string"):
        _parse_tool_arguments(123)


def test_parse_tool_arguments_raises_on_invalid_json() -> None:
    from executionkit.provider import _parse_tool_arguments

    with pytest.raises(ProviderError, match="were not valid JSON"):
        _parse_tool_arguments("{bad json}")


def test_parse_tool_arguments_redacts_invalid_json_secret() -> None:
    from executionkit.provider import _parse_tool_arguments

    with pytest.raises(ProviderError) as exc_info:
        _parse_tool_arguments('{"api_key":"ghp_1234567890abcdef"')

    message = str(exc_info.value)
    assert "ghp_1234567890abcdef" not in message
    assert "[REDACTED]" in message


def test_parse_tool_arguments_raises_on_non_object_json() -> None:
    from executionkit.provider import _parse_tool_arguments

    with pytest.raises(ProviderError, match="decode to a JSON object"):
        _parse_tool_arguments('["not","object"]')


def test_load_json_handles_empty_and_valid_object() -> None:
    from executionkit.provider import _load_json

    assert _load_json(b"") == {}
    assert _load_json(b'{"ok": true}') == {"ok": True}


def test_load_json_raises_on_invalid_utf8_or_json() -> None:
    from executionkit.provider import _load_json

    with pytest.raises(ProviderError, match="non-JSON data"):
        _load_json(b"\xff\xfe")

    with pytest.raises(ProviderError, match="non-JSON data"):
        _load_json(b"{bad json}")


def test_load_json_raises_on_non_object_json() -> None:
    from executionkit.provider import _load_json

    with pytest.raises(ProviderError, match="non-object JSON payload"):
        _load_json(b'["not","object"]')


def test_format_http_error_uses_string_error_field() -> None:
    from executionkit.provider import _format_http_error

    result = _format_http_error(500, {"error": "token secret-abcdef failed"})
    assert "secret-abcdef" not in result
    assert "[REDACTED]" in result


def test_format_http_error_falls_back_without_message() -> None:
    from executionkit.provider import _format_http_error

    assert _format_http_error(502, {"error": {"code": "bad_gateway"}}) == (
        "Provider request failed with HTTP 502"
    )


async def test_urllib_read_timeout_maps_to_retryable_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from executionkit.cost import CostTracker
    from executionkit.engine.retry import RetryConfig
    from executionkit.patterns.base import checked_complete

    class TimeoutResponse:
        def __enter__(self) -> TimeoutResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            raise TimeoutError("read timed out")

    def fake_urlopen(*args: object, **kwargs: object) -> TimeoutResponse:
        return TimeoutResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = Provider(base_url="http://example.test/v1", model="m")
    object.__setattr__(provider, "_use_httpx", False)
    object.__setattr__(provider, "_client", None)
    tracker = CostTracker()

    with pytest.raises(ProviderError, match="Transport failure"):
        await checked_complete(
            provider,
            [{"role": "user", "content": "hi"}],
            tracker,
            None,
            RetryConfig(max_retries=2, base_delay=0.0),
        )

    assert tracker.call_count == 2


async def test_httpx_transport_failure_redacts_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not Provider(base_url="http://x", model="m")._use_httpx:
        pytest.skip("httpx backend not active")

    provider = Provider(base_url="http://x", model="m")

    class Client:
        async def post(self, *args: object, **kwargs: object) -> object:
            import httpx

            raise httpx.TransportError("failed with ghp_1234567890abcdef")

    object.__setattr__(provider, "_client", Client())

    with pytest.raises(ProviderError) as exc_info:
        await provider._post("chat/completions", {})

    message = str(exc_info.value)
    assert "ghp_1234567890abcdef" not in message
    assert "[REDACTED]" in message


# ---------------------------------------------------------------------------
# _parse_retry_after: RFC 7231 header parsing
# ---------------------------------------------------------------------------


class TestParseRetryAfter:
    """_parse_retry_after handles numeric seconds, HTTP-dates, and garbage."""

    def _call(self, value: str) -> float:
        from executionkit.provider import _parse_retry_after

        return _parse_retry_after(value)

    def test_numeric_integer_seconds(self) -> None:
        """Integer-string Retry-After header returns that many seconds."""
        result = self._call("30")
        assert result == 30.0

    def test_numeric_float_seconds(self) -> None:
        """Float-string Retry-After header returns the float value."""
        result = self._call("2.5")
        assert result == 2.5

    def test_numeric_zero_seconds(self) -> None:
        """Zero-second Retry-After header returns 0.0 (non-negative)."""
        result = self._call("0")
        assert result == 0.0

    def test_http_date_returns_positive_delta(self) -> None:
        """An HTTP-date far in the future produces a positive delay in seconds."""
        import email.utils
        from datetime import UTC, datetime, timedelta

        future = datetime.now(tz=UTC) + timedelta(seconds=120)
        http_date = email.utils.format_datetime(future)
        result = self._call(http_date)
        # Allow a 5-second window for test execution time
        assert 115.0 <= result <= 125.0

    def test_garbage_value_returns_default(self) -> None:
        """Unrecognised header value falls back to the default (1.0)."""
        result = self._call("not-a-date-or-number")
        assert result == 1.0

    def test_garbage_with_custom_default(self) -> None:
        """Garbage header value returns the caller-supplied default."""
        from executionkit.provider import _parse_retry_after

        result = _parse_retry_after("??", default=5.0)
        assert result == 5.0

    def test_positive_infinity_returns_default(self) -> None:
        """``"inf"`` is non-finite and must not become an unbounded sleep delay."""
        result = self._call("inf")
        assert result == 1.0

    def test_nan_returns_default(self) -> None:
        """``"nan"`` is non-finite and falls back to the default delay."""
        result = self._call("nan")
        assert result == 1.0

    def test_negative_infinity_returns_default(self) -> None:
        """``"-inf"`` is non-finite and falls back to the default delay."""
        result = self._call("-inf")
        assert result == 1.0


# ---------------------------------------------------------------------------
# SEC-01: ToolCall.arguments is immutable (MappingProxyType)
# ---------------------------------------------------------------------------


class TestToolCallImmutability:
    """ToolCall.arguments must be wrapped in MappingProxyType to prevent mutation."""

    def test_arguments_is_mapping_proxy(self) -> None:
        """Plain dict passed to ToolCall is wrapped in MappingProxyType."""
        from types import MappingProxyType

        tc = ToolCall(id="t1", name="fn", arguments={"x": 1})
        assert isinstance(tc.arguments, MappingProxyType)

    def test_arguments_mutation_raises_type_error(self) -> None:
        """Attempting to set a key on ToolCall.arguments must raise TypeError."""
        tc = ToolCall(id="t1", name="fn", arguments={"x": 1})
        with pytest.raises(TypeError):
            tc.arguments["x"] = 99  # type: ignore[index]

    def test_arguments_deletion_raises_type_error(self) -> None:
        """Attempting to delete a key on ToolCall.arguments must raise TypeError."""
        tc = ToolCall(id="t1", name="fn", arguments={"x": 1})
        with pytest.raises(TypeError):
            del tc.arguments["x"]  # type: ignore[attr-defined]

    def test_arguments_content_is_preserved(self) -> None:
        """Wrapping must not alter the contents of the arguments dict."""
        tc = ToolCall(id="t1", name="fn", arguments={"a": 1, "b": "hello"})
        assert tc.arguments["a"] == 1
        assert tc.arguments["b"] == "hello"

    def test_arguments_spread_still_works(self) -> None:
        """``**tc.arguments`` unpacking must work for downstream tool dispatch."""

        def _tool(a: int, b: str) -> str:
            return f"{a}-{b}"

        tc = ToolCall(id="t1", name="fn", arguments={"a": 42, "b": "world"})
        result = _tool(**tc.arguments)
        assert result == "42-world"

    def test_already_proxy_is_not_double_wrapped(self) -> None:
        """Passing a MappingProxyType directly must not re-wrap it."""
        from types import MappingProxyType

        proxy = MappingProxyType({"k": "v"})
        tc = ToolCall(id="t1", name="fn", arguments=proxy)
        assert tc.arguments is proxy


# ---------------------------------------------------------------------------
# SEC-02: SSRF scheme validation — Provider rejects non-http(s) base_url
# ---------------------------------------------------------------------------


class TestProviderSchemeValidation:
    """Provider.__post_init__ must reject URL schemes other than http and https."""

    @pytest.mark.parametrize(
        "bad_url",
        [
            "file:///etc/passwd",
            "ftp://attacker.internal/llm",
            "gopher://evil.internal:70/",
            "data:text/plain,hello",
            "javascript:alert(1)",
            "dict://localhost:2628/",
        ],
    )
    def test_non_http_scheme_raises_value_error(self, bad_url: str) -> None:
        """Non-http(s) URL scheme must raise ValueError at construction time."""
        with pytest.raises(ValueError, match="scheme must be 'http' or 'https'"):
            Provider(base_url=bad_url, model="m")

    def test_http_localhost_is_accepted(self) -> None:
        """http://localhost is a valid base_url (local LLM servers like Ollama)."""
        p = Provider(base_url="http://localhost:11434/v1", model="llama3.2")
        assert p.base_url == "http://localhost:11434/v1"

    def test_http_127_is_accepted(self) -> None:
        """http://127.0.0.1 must not be blocked."""
        p = Provider(base_url="http://127.0.0.1:8080/v1", model="m")
        assert p.base_url == "http://127.0.0.1:8080/v1"

    def test_https_remote_is_accepted(self) -> None:
        """https:// remote endpoints must be accepted."""
        p = Provider(base_url="https://api.example.com/v1", model="gpt-4o")
        assert p.base_url == "https://api.example.com/v1"

    def test_http_private_range_is_accepted(self) -> None:
        """Private-range IPs are legitimate LLM server addresses and must pass."""
        p = Provider(base_url="http://192.168.1.100:11434/v1", model="llama3.2")
        assert p.base_url == "http://192.168.1.100:11434/v1"

    def test_error_message_includes_offending_scheme(self) -> None:
        """ValueError message must name the offending scheme for debuggability."""
        with pytest.raises(ValueError, match="file://"):
            Provider(base_url="file:///etc/passwd", model="m")


# ---------------------------------------------------------------------------
# SEC-03: _redact_sensitive broadened coverage
# ---------------------------------------------------------------------------


class TestRedactSensitiveBroadened:
    """_redact_sensitive must catch additional key-name and boundary variants."""

    def _redact(self, text: str) -> str:
        from executionkit.provider import _redact_sensitive

        return _redact_sensitive(text)

    # --- case-insensitive key-name variants ---

    def test_api_key_equals_lowercase(self) -> None:
        result = self._redact("api_key=sk-supersecretvalue")
        assert "sk-supersecretvalue" not in result
        assert "[REDACTED]" in result

    def test_api_key_equals_uppercase(self) -> None:
        result = self._redact("API_KEY=sk-supersecretvalue")
        assert "sk-supersecretvalue" not in result
        assert "[REDACTED]" in result

    def test_apikey_no_underscore(self) -> None:
        result = self._redact("apikey=supersecretvalue1234")
        assert "supersecretvalue1234" not in result
        assert "[REDACTED]" in result

    def test_password_equals(self) -> None:
        result = self._redact("password=hunter2hunter")
        assert "hunter2hunter" not in result
        assert "[REDACTED]" in result

    def test_password_equals_uppercase(self) -> None:
        result = self._redact("PASSWORD=hunter2hunter")
        assert "hunter2hunter" not in result
        assert "[REDACTED]" in result

    def test_access_key_equals(self) -> None:
        result = self._redact("access_key=AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED]" in result

    # --- URL query-string boundary forms ---

    def test_query_string_api_key(self) -> None:
        """?api_key=VALUE in a URL must be redacted."""
        result = self._redact("https://api.example.com/v1?api_key=supersecretval")
        assert "supersecretval" not in result
        assert "[REDACTED]" in result

    def test_query_string_ampersand_api_key(self) -> None:
        """&api_key=VALUE (subsequent query param) must be redacted."""
        result = self._redact(
            "https://api.example.com/v1?foo=bar&api_key=supersecretval"
        )
        assert "supersecretval" not in result
        assert "[REDACTED]" in result

    def test_query_string_password(self) -> None:
        result = self._redact("https://host/?password=mypassword12")
        assert "mypassword12" not in result
        assert "[REDACTED]" in result

    # --- safe words must NOT be over-redacted ---

    def test_ordinary_word_not_redacted(self) -> None:
        """Common words that happen to contain 'key' must not be redacted."""
        result = self._redact("The monkey ate the turkey.")
        assert result == "The monkey ate the turkey."

    def test_short_value_not_redacted(self) -> None:
        """Values shorter than 4 chars after '=' must not match (too short)."""
        result = self._redact("key=abc")
        # 'abc' is 3 chars — below threshold
        assert "[REDACTED]" not in result
