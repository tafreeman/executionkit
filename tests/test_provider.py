"""Tests for provider.py — error hierarchy, value types, and Provider class."""

from __future__ import annotations

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

    def test_dual_format_input_tokens_zero_not_falsy(self) -> None:
        # input_tokens=0 (e.g. cached prompt) must NOT fall back to prompt_tokens
        r = LLMResponse(
            content="",
            usage=MappingProxyType({"input_tokens": 0, "prompt_tokens": 99}),
        )
        assert r.input_tokens == 0


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


@pytest.mark.asyncio
async def test_post_maps_5xx_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = Provider("https://example.com/v1", model="test-model")

    def fake_urlopen(*args: object, **kwargs: object) -> object:
        raise error.HTTPError(
            url="https://example.com/v1/chat/completions",
            code=500,
            msg="Internal Server Error",
            hdrs={},
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_aclose_noop_without_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """aclose() is a no-op when the urllib backend is active."""
    import executionkit.provider as pmod

    monkeypatch.setattr(pmod, "_HTTPX_AVAILABLE", False)
    monkeypatch.setattr(pmod, "_httpx", None)

    provider = Provider("https://example.com/v1", model="test-model")
    assert provider._use_httpx is False
    # Must not raise
    await provider.aclose()


@pytest.mark.asyncio
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
