"""LLM provider, response types, and error hierarchy.

Implements a single ``Provider`` class that speaks the OpenAI-compatible
``/chat/completions`` JSON format over stdlib ``urllib``.  Also defines the
``LLMProvider`` structural protocol, frozen value types (``LLMResponse``,
``ToolCall``), and the full 9-class error tree.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import email.utils
import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, NoReturn, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping, Sequence
    from types import TracebackType

# Re-export the error hierarchy from errors.py using the `Name as Name` idiom
# so ruff/mypy recognise these as intentional public re-exports.
# Existing `from executionkit.provider import XError` imports continue to work.
# Ref: PEP 387 backwards-compat — https://peps.python.org/pep-0387/
from executionkit.errors import BudgetExhaustedError as BudgetExhaustedError
from executionkit.errors import ConsensusFailedError as ConsensusFailedError
from executionkit.errors import ExecutionKitError as ExecutionKitError
from executionkit.errors import LLMError as LLMError
from executionkit.errors import MaxIterationsError as MaxIterationsError
from executionkit.errors import PatternError as PatternError
from executionkit.errors import PermanentError as PermanentError
from executionkit.errors import ProviderError as ProviderError
from executionkit.errors import RateLimitError as RateLimitError
from executionkit.observability import llm_span, record_llm_span_attributes

# ---------------------------------------------------------------------------
# httpx availability probe (done once at import time)
# ---------------------------------------------------------------------------

try:
    import httpx as _httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Error hierarchy — defined in errors.py; re-exported here so that existing
# `from executionkit.provider import XError` imports continue to work.
# PEP 387 backwards-compatibility: https://peps.python.org/pep-0387/
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

MAX_PROVIDER_REPORTED_TOKENS = 1_000_000_000

# HTTP status at or above which a response is treated as an error.
HTTP_ERROR_THRESHOLD = 400

# SSE framing tokens for OpenAI-compatible streaming responses.
_SSE_DATA_PREFIX = "data:"
_SSE_DONE_SENTINEL = "[DONE]"


def _usage_int(value: Any, field_name: str) -> int:
    """Return a bounded non-negative integer token count."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProviderError(f"{field_name} usage must be an integer")
    if value < 0:
        raise ProviderError(f"{field_name} usage cannot be negative")
    if value > MAX_PROVIDER_REPORTED_TOKENS:
        raise ProviderError(f"{field_name} usage is unreasonably large")
    return value


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool invocation extracted from an LLM response."""

    id: str
    name: str
    # Declared as Mapping so callers receive a read-only view; __post_init__
    # wraps any plain dict in MappingProxyType.  ``**tc.arguments`` unpacking
    # still works because MappingProxyType supports the mapping protocol.
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        """Wrap ``arguments`` in a read-only proxy to enforce immutability."""
        if not isinstance(self.arguments, MappingProxyType):
            object.__setattr__(
                self, "arguments", MappingProxyType(dict(self.arguments))
            )


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Parsed LLM completion response.

    Handles both OpenAI (``prompt_tokens`` / ``completion_tokens``) and
    Anthropic (``input_tokens`` / ``output_tokens``) usage key formats.

    The library redacts ``content`` before emitting it in any trace it owns.
    ``raw`` is the verbatim, *unredacted* provider payload and is therefore
    caller-owned: the library never emits it, and a caller that logs or traces
    ``raw`` is responsible for redacting any credentials it may contain.
    """

    content: str
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    finish_reason: str = "stop"
    usage: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    # Unredacted, caller-owned provider payload — see the class docstring.
    raw: Any = None

    @property
    def input_tokens(self) -> int:
        u = self.usage
        if "input_tokens" in u:
            return _usage_int(u["input_tokens"], "input_tokens")
        return _usage_int(u.get("prompt_tokens", 0), "prompt_tokens")

    @property
    def output_tokens(self) -> int:
        u = self.usage
        if "output_tokens" in u:
            return _usage_int(u["output_tokens"], "output_tokens")
        return _usage_int(u.get("completion_tokens", 0), "completion_tokens")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def was_truncated(self) -> bool:
        return self.finish_reason in {"length", "max_tokens"}


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Structural protocol for any LLM backend.

    Any class with a matching ``complete`` signature satisfies this protocol
    via structural subtyping (PEP 544) — no explicit inheritance required.
    """

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...


@runtime_checkable
class ToolCallingProvider(LLMProvider, Protocol):
    """Extension of ``LLMProvider`` for providers that support tool calling.

    The built-in :class:`Provider` satisfies this protocol via its
    ``supports_tools`` attribute.  Pass to :func:`react_loop` to unlock
    tool-calling patterns.
    """

    supports_tools: Literal[True]


@runtime_checkable
class StreamingProvider(LLMProvider, Protocol):
    """Extension of ``LLMProvider`` for providers that can stream completions.

    A streaming provider yields incremental text deltas via :meth:`stream`
    instead of returning a single :class:`LLMResponse`.  ``stream`` is a normal
    (non-``async``) method that *returns* an async iterator — call it without
    ``await`` and consume the result with ``async for``.  Satisfied
    structurally (PEP 544); the built-in :class:`Provider` and the test
    :class:`~executionkit._mock.MockProvider` both implement it.
    """

    def stream(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        usage_sink: list[LLMResponse] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]: ...


def _provider_supports_tools(provider: object) -> bool:
    """Return True only when *provider* both structurally satisfies
    ``ToolCallingProvider`` AND has ``supports_tools`` set to ``True``.

    ``@runtime_checkable`` protocols only verify that the required
    attribute *exists*, not that its value is ``True``.  A wrapper with
    ``supports_tools = False`` would pass ``isinstance(p, ToolCallingProvider)``
    — this helper closes that gap so both ``kit.py`` and ``react_loop.py``
    use a single, consistent capability check.
    """
    return isinstance(provider, ToolCallingProvider) and (
        getattr(provider, "supports_tools", False) is True
    )


# ---------------------------------------------------------------------------
# Concrete provider
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Provider:
    """Universal LLM provider. Posts JSON, parses JSON. No SDK needed.

    Works with any OpenAI-compatible endpoint: OpenAI, Azure, Ollama,
    Together, Groq, GitHub Models, etc.
    """

    base_url: str
    model: str
    api_key: str = ""
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    timeout: float = 120.0
    # supports_tools is Literal[True] for this concrete HTTP client because
    # it always speaks the OpenAI tool-calling wire format.
    # WARNING (F-04): If you build a *wrapper* around Provider, do NOT copy
    # this attribute verbatim — delegate instead:
    #   @property
    #   def supports_tools(self) -> bool: return self._inner.supports_tools
    # For @runtime_checkable protocols, isinstance(wrapper, ToolCallingProvider)
    # only checks that the required attribute exists, not whether its value is
    # True. Delegating keeps the wrapper's reported capability aligned with the
    # inner provider's actual tool support.
    supports_tools: Literal[True] = field(default=True, init=False)
    # Derived state — excluded from repr/eq/hash; initialized only in __post_init__
    _client: Any = field(
        default=None, init=False, repr=False, compare=False, hash=False
    )
    _use_httpx: bool = field(
        default=False, init=False, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        # --- SSRF scheme guard (trust boundary) ----------------------------
        # base_url is a trust boundary: callers control this value, so we
        # validate the URL scheme before any network activity to prevent
        # file://, ftp://, gopher://, data://, etc. attacks.
        # Localhost and private-range IPs are intentionally NOT blocked —
        # local LLM servers (Ollama, LM Studio, vLLM) are a primary use case.
        scheme = self.base_url.split("://", maxsplit=1)[0].lower()
        if scheme not in {"http", "https"}:
            raise ValueError(
                f"base_url scheme must be 'http' or 'https', got '{scheme}://'. "
                "Use an http:// or https:// URL (e.g. http://localhost:11434/v1)."
            )
        # --- HTTP client setup -------------------------------------------
        # object.__setattr__ is the standard pattern for derived state on frozen
        # dataclasses.
        # follow_redirects=False prevents auth-header leakage: a 302 to an
        # internal host would otherwise resend the Authorization header.
        if _HTTPX_AVAILABLE and _httpx is not None:
            object.__setattr__(
                self,
                "_client",
                _httpx.AsyncClient(timeout=self.timeout, follow_redirects=False),
            )
            object.__setattr__(self, "_use_httpx", True)
        else:
            object.__setattr__(self, "_client", None)
            object.__setattr__(self, "_use_httpx", False)

    def __repr__(self) -> str:
        masked = "***" if self.api_key else ""
        return (
            f"Provider(base_url={self.base_url!r}, model={self.model!r}, "
            f"api_key={masked!r})"
        )

    async def aclose(self) -> None:
        """Release the underlying HTTP client.

        Call this when the provider is no longer needed (or use it as an
        async context manager instead).
        """
        if self._use_httpx and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> Provider:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """POST to ``{base_url}/chat/completions`` and parse the JSON response."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": (
                temperature if temperature is not None else self.default_temperature
            ),
            "max_tokens": (
                max_tokens if max_tokens is not None else self.default_max_tokens
            ),
        }
        if tools:
            payload["tools"] = list(tools)
        payload.update(kwargs)

        with llm_span(self.model) as span:
            data = await self._post("chat/completions", payload)
            response = self._parse_response(data)
            record_llm_span_attributes(
                span,
                self.model,
                response.input_tokens,
                response.output_tokens,
            )
            return response

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Route to the appropriate HTTP backend."""
        url, body, headers = self._prepare_request(endpoint, payload)
        if self._use_httpx:
            return await self._post_httpx(url, body, headers)
        return await self._post_urllib(url, body, headers)

    def _prepare_request(
        self, endpoint: str, payload: dict[str, Any]
    ) -> tuple[str, bytes, dict[str, str]]:
        """Build the ``(url, body, headers)`` triple for an API request."""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        body = json.dumps(payload).encode()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return url, body, headers

    async def _post_httpx(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """HTTP POST via ``httpx.AsyncClient`` with connection pooling."""
        assert _httpx is not None  # noqa: S101
        try:
            resp = await self._client.post(url, content=body, headers=headers)
            resp.raise_for_status()
            raw: dict[str, Any] = resp.json()
            return raw
        except _httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            try:
                raw = exc.response.json()
                if not isinstance(raw, dict):
                    raw = {}
            except Exception:
                raw = {}
            retry_after = _parse_retry_after(
                exc.response.headers.get("retry-after", "1")
            )
            _classify_http_error(status, raw, retry_after, cause=exc)
        except _httpx.TransportError as exc:
            raise ProviderError(
                f"Transport failure: {_redact_sensitive(str(exc))}"
            ) from exc

    async def _post_urllib(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """HTTP POST via stdlib ``urllib`` in a thread.

        Maps HTTP errors to the appropriate error class via
        :func:`_classify_http_error`:
        - 429 -> RateLimitError
        - {400, 401, 403, 404, 405, 413, 422} -> PermanentError
          (non-retryable client errors whose outcome cannot change on retry)
        - everything else >=400 -> ProviderError (retryable by default)

        The ``Authorization`` header is added as an *unredirected* header so
        urllib will NOT resend the bearer credential if the endpoint issues a
        cross-host redirect (prevents auth-header leakage on redirect).
        """
        request_timeout = self.timeout

        def _sync() -> dict[str, Any]:
            req = urllib.request.Request(url, data=body)  # noqa: S310
            for name, value in headers.items():
                # Authorization is added unredirected so it is not leaked to a
                # redirected host; other headers may safely follow redirects.
                if name.lower() == "authorization":
                    req.add_unredirected_header(name, value)
                else:
                    req.add_header(name, value)
            try:
                with urllib.request.urlopen(  # noqa: S310
                    req, timeout=request_timeout
                ) as resp:
                    raw: dict[str, Any] = json.loads(resp.read())
                    return raw
            except urllib.error.HTTPError as exc:
                try:
                    raw = _load_json(exc.read())
                except ProviderError:
                    raw = {}
                status = exc.code
                retry_after = _parse_retry_after(
                    exc.headers.get("retry-after", "1") if exc.headers else "1"
                )
                _classify_http_error(status, raw, retry_after, cause=exc)
            except urllib.error.URLError as exc:
                raise ProviderError(
                    f"Transport failure: {_redact_sensitive(str(exc.reason))}"
                ) from exc
            except TimeoutError as exc:
                raise ProviderError(
                    f"Transport failure: {_redact_sensitive(str(exc))}"
                ) from exc

        return await asyncio.to_thread(_sync)

    def stream(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        usage_sink: list[LLMResponse] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a completion as live text deltas over OpenAI-compatible SSE.

        Sends ``stream: true`` plus ``stream_options.include_usage`` so the
        server emits a final usage frame.  Yields ``choices[0].delta.content``
        strings as they arrive.  When *usage_sink* is supplied, the final
        :class:`LLMResponse` (carrying token usage) is appended to it once the
        stream drains, so budget-aware callers can record cost afterwards.

        This is a regular method that *returns* an async iterator — call it
        without ``await`` and consume it with ``async for``.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": (
                temperature if temperature is not None else self.default_temperature
            ),
            "max_tokens": (
                max_tokens if max_tokens is not None else self.default_max_tokens
            ),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = list(tools)
        payload.update(kwargs)
        return self._stream(payload, usage_sink)

    async def _stream(
        self,
        payload: dict[str, Any],
        usage_sink: list[LLMResponse] | None,
    ) -> AsyncIterator[str]:
        """Drive the SSE transport, parse frames, and yield content deltas."""
        url, body, headers = self._prepare_request("chat/completions", payload)
        raw_lines = (
            self._stream_httpx(url, body, headers)
            if self._use_httpx
            else self._stream_urllib(url, body, headers)
        )
        parts: list[str] = []
        final: LLMResponse | None = None
        with llm_span(self.model) as span:
            async for line in raw_lines:
                chunk = _parse_sse_line(line)
                if chunk is None:
                    continue
                delta = _extract_stream_delta(chunk)
                if delta is not None:
                    parts.append(delta)
                    yield delta
                usage_response = _response_from_usage_chunk(chunk, "".join(parts))
                if usage_response is not None:
                    final = usage_response
            if final is None:
                final = LLMResponse(content="".join(parts))
            if usage_sink is not None:
                usage_sink.append(final)
            record_llm_span_attributes(
                span, self.model, final.input_tokens, final.output_tokens
            )

    async def _stream_httpx(  # pragma: no cover - needs a live SSE server
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> AsyncIterator[str]:
        """Yield raw SSE lines via ``httpx.AsyncClient.stream``."""
        assert _httpx is not None  # noqa: S101
        try:
            async with self._client.stream(
                "POST", url, content=body, headers=headers
            ) as resp:
                if resp.status_code >= HTTP_ERROR_THRESHOLD:
                    await resp.aread()
                    _raise_httpx_stream_error(resp)
                async for line in resp.aiter_lines():
                    yield line
        except _httpx.TransportError as exc:
            raise ProviderError(
                f"Transport failure: {_redact_sensitive(str(exc))}"
            ) from exc

    async def _stream_urllib(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> AsyncIterator[str]:
        """Yield raw SSE lines via stdlib ``urllib`` on a worker thread.

        urllib is synchronous, so a producer thread reads the response line by
        line and hands each line to the event loop through an
        :class:`asyncio.Queue` (scheduled with ``call_soon_threadsafe``).  The
        async generator awaits the queue, yielding lines as they arrive without
        blocking the loop.  ``Authorization`` is added as an *unredirected*
        header so the bearer credential is never resent across a redirect.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()
        request_timeout = self.timeout

        def _put(item: str | BaseException | None) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def _producer() -> None:
            try:
                req = urllib.request.Request(url, data=body)  # noqa: S310
                for name, value in headers.items():
                    if name.lower() == "authorization":
                        req.add_unredirected_header(name, value)
                    else:
                        req.add_header(name, value)
                try:
                    with urllib.request.urlopen(  # noqa: S310
                        req, timeout=request_timeout
                    ) as resp:
                        for raw_line in resp:
                            _put(raw_line.decode("utf-8").rstrip("\r\n"))
                except urllib.error.HTTPError as exc:
                    _put(_stream_http_error_urllib(exc))
                except urllib.error.URLError as exc:
                    _put(
                        ProviderError(
                            f"Transport failure: {_redact_sensitive(str(exc.reason))}"
                        )
                    )
                except TimeoutError as exc:
                    _put(
                        ProviderError(
                            f"Transport failure: {_redact_sensitive(str(exc))}"
                        )
                    )
            finally:
                _put(None)

        producer = loop.run_in_executor(None, _producer)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            await producer

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """Extract content, tool calls, and usage from the raw API response."""
        choice = _first_choice(data)
        message = choice.get("message", {})
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return LLMResponse(
            content=_extract_content(message.get("content")),
            tool_calls=tuple(_parse_tool_calls(message.get("tool_calls"))),
            finish_reason=str(choice.get("finish_reason", "stop")),
            usage=MappingProxyType(dict(usage)),
            raw=data,
        )


def _first_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("Provider response did not include any choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ProviderError("Provider choice payload was not an object")
    return choice


def _extract_text_value(text: Any) -> str | None:
    """Return the string value nested inside a ``text`` field, or ``None``."""
    if isinstance(text, str):
        return text
    if isinstance(text, dict):
        value = text.get("value")
        if isinstance(value, str):
            return value
    return None


def _extract_content_item(item: Any) -> str | None:
    """Return the text contribution of a single content-list item, or ``None``."""
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return None
    if item.get("type") in {"text", "output_text"}:
        return _extract_text_value(item.get("text"))
    value = item.get("value")
    if isinstance(value, str):
        return value
    return None


def _extract_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            part = _extract_content_item(item)
            if part is not None:
                parts.append(part)
        return "".join(parts)
    return str(content)


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    if raw_tool_calls is None:
        return []
    if not isinstance(raw_tool_calls, list):
        raise ProviderError("tool_calls payload was not a list")
    parsed: list[ToolCall] = []
    for raw_tc in raw_tool_calls:
        if not isinstance(raw_tc, dict):
            raise ProviderError("tool_call payload was not an object")
        function = raw_tc.get("function")
        if not isinstance(function, dict):
            raise ProviderError("tool_call.function payload was not an object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise ProviderError("tool_call.function.name was missing")
        arguments = _parse_tool_arguments(function.get("arguments"))
        tool_id = raw_tc.get("id")
        parsed.append(
            ToolCall(
                id=tool_id if isinstance(tool_id, str) else "",
                name=name,
                arguments=arguments,
            )
        )
    return parsed


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str):
        raise ProviderError("tool_call arguments must be a dict or JSON string")
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"tool_call arguments were not valid JSON: {_redact_sensitive(arguments)}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderError("tool_call arguments must decode to a JSON object")
    return parsed


def _load_json(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("Provider returned non-JSON data") from exc
    if not isinstance(loaded, dict):
        raise ProviderError("Provider returned a non-object JSON payload")
    return loaded


def _redact_sensitive(text: str) -> str:
    """Replace credential-like substrings with ``[REDACTED]``.

    Matches common API key/token shapes and authorization phrases.
    Case-insensitive so ``API_KEY=``, ``api_key=``, ``Password=`` etc. are
    all caught.  Also handles URL query-string boundaries (``?`` / ``&``)
    where a word boundary ``\\b`` anchor does not fire.
    """
    return re.sub(
        r"""(?ix)
        # Named-service token patterns (prefix-anchored, no false positives)
        \b(?:
            gh[pousr]_[A-Za-z0-9_]{4,}
            | AIza[A-Za-z0-9_-]{8,}
            | xox[bpoa]-[A-Za-z0-9-]{8,}
            | gsk_[A-Za-z0-9_]{4,}
            | sk[-_][^\s'"<>]{4,}
        )
        |
        # Key-name=value pairs — word-boundary OR query-string boundary (?/&).
        # The alternation handles both:
        #   word-boundary form:   key=VALUE
        #   URL query-string:     ?api_key=VALUE  or  &api_key=VALUE
        # Covers: api_key, apikey, access_key, password, passwd, key, token,
        #         secret, auth, and their uppercase / underscore variants.
        (?:\b|(?<=[?&]))
        (?:api_?key|access_?key|password|passwd|key|token|secret|auth)
        [=:][^\s'"<>&]{4,}
        |
        # "Bearer <value>", "token <value>", "secret <value>" (case-insensitive)
        \b(?:bearer|token|secret)\s+[A-Za-z0-9._~+/\-=]{4,}
        """,
        "[REDACTED]",
        text,
    )


def _parse_retry_after(header_value: str, default: float = 1.0) -> float:
    """Parse a ``Retry-After`` header value into a non-negative delay in seconds.

    RFC 7231 allows the value to be either a decimal number of seconds or an
    HTTP-date string (e.g. ``"Wed, 18 Jun 2026 07:28:00 GMT"``).  A bare
    ``float()`` call raises ``ValueError`` on dates, crashing the error path.

    Resolution order:
    1. Integer / float seconds — the common case.
    2. HTTP-date parsed with ``email.utils.parsedate_to_datetime`` — RFC 7231
       compliant dates.
    3. ``default`` — when both parses fail (garbage value).

    Args:
        header_value: Raw string from the ``Retry-After`` response header.
        default: Fallback delay in seconds (default 1.0).

    Returns:
        Non-negative float seconds to wait before the next attempt.
    """
    # 1. Try numeric seconds first (the common case).  ``float()`` also parses
    #    "inf"/"-inf"/"nan"; a non-finite delay would flow into asyncio.sleep
    #    and hang the retry coroutine forever, so reject it and fall through.
    try:
        value = float(header_value)
    except ValueError:
        pass
    else:
        if math.isfinite(value):
            return max(0.0, value)

    # 2. RFC 7231 HTTP-date; any parse/compute failure falls back to the default.
    #    parsedate_to_datetime raises ValueError on malformed input, and a naive
    #    result would raise TypeError on the aware-datetime subtraction below.
    try:
        retry_dt = email.utils.parsedate_to_datetime(header_value)
        delta = (retry_dt - _dt.datetime.now(tz=_dt.UTC)).total_seconds()
    except (TypeError, ValueError):
        return default
    return max(0.0, delta)


def _classify_http_error(
    status: int,
    raw: dict[str, Any],
    retry_after: float,
    *,
    cause: BaseException,
) -> NoReturn:
    """Raise the correct LLM error subclass for a failed HTTP response.

    Extracted to eliminate duplication between the urllib and httpx backends.
    Both backends call this single function — the exact pattern used by the
    Anthropic SDK's ``_make_status_error()`` method.

    Ref: https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_client.py

    Args:
        status: HTTP status code from the failed response.
        raw: Parsed JSON body from the response (may be empty dict).
        retry_after: Value of the ``Retry-After`` header in seconds.
        cause: The original exception, chained via ``raise ... from cause``.

    Raises:
        RateLimitError: For HTTP 429.
        PermanentError: For HTTP 401, 403, 404, 400, 405, 413, 422.
            These statuses indicate a permanent client error — the request
            cannot succeed as-is regardless of how many times it is retried.
            Mapping them to ``PermanentError`` (which is not in the default
            ``RetryConfig.retryable`` tuple) prevents burning the LLM call
            budget on outcomes that cannot change (e.g. malformed request,
            unprocessable entity, payload too large).
        ProviderError: For 5xx and all other non-2xx status codes, which may
            be transient and are therefore retryable under the default config.
    """
    if status == 429:
        raise RateLimitError(
            "Rate limited (HTTP 429)",
            retry_after=retry_after,
        ) from cause
    # Non-retryable client errors: the request cannot succeed as-is.
    # 400 = bad request, 405 = method not allowed,
    # 413 = payload too large, 422 = unprocessable entity.
    # Note: 408 (Request Timeout) and 409 (Conflict) are intentionally
    # excluded — 408 is a transient server-side timeout, and 409 can be a
    # transient lock/conflict that OpenAI-compatible clients retry; both
    # remain retryable as ProviderError.
    # Note: 429 is handled above as RateLimitError, not PermanentError.
    if status in {400, 401, 403, 404, 405, 413, 422}:
        raise PermanentError(_format_http_error(status, raw)) from cause
    # 5xx and other unknown statuses may be transient — keep as ProviderError
    # so they remain retryable under the default RetryConfig.
    raise ProviderError(_format_http_error(status, raw)) from cause


def _format_http_error(status_code: int, payload: dict[str, Any]) -> str:
    message = payload.get("error")
    if isinstance(message, dict):
        detail = message.get("message")
        if isinstance(detail, str):
            return (
                f"Provider request failed with HTTP {status_code}: "
                f"{_redact_sensitive(detail)}"
            )
    if isinstance(message, str):
        return (
            f"Provider request failed with HTTP {status_code}: "
            f"{_redact_sensitive(message)}"
        )
    return f"Provider request failed with HTTP {status_code}"


# ---------------------------------------------------------------------------
# Streaming SSE helpers
# ---------------------------------------------------------------------------


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    """Decode one SSE ``data:`` line into a JSON object.

    Returns ``None`` for blank lines, non-``data:`` lines (e.g. ``event:`` or
    SSE comments), and the terminal ``[DONE]`` sentinel.  Raises
    :exc:`ProviderError` if a data payload is present but not a JSON object.
    """
    stripped = line.strip()
    if not stripped or not stripped.startswith(_SSE_DATA_PREFIX):
        return None
    data = stripped[len(_SSE_DATA_PREFIX) :].strip()
    if not data or data == _SSE_DONE_SENTINEL:
        return None
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider returned a non-JSON SSE data frame") from exc
    if not isinstance(chunk, dict):
        raise ProviderError("Provider SSE data frame was not a JSON object")
    return chunk


def _extract_stream_delta(chunk: dict[str, Any]) -> str | None:
    """Return ``choices[0].delta.content`` from an SSE chunk, or ``None``."""
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return None
    content = delta.get("content")
    return content if isinstance(content, str) else None


def _response_from_usage_chunk(
    chunk: dict[str, Any], content: str
) -> LLMResponse | None:
    """Build an :class:`LLMResponse` from a chunk carrying a ``usage`` object.

    OpenAI emits a terminal chunk (empty ``choices``) carrying token usage when
    ``stream_options.include_usage`` is set.  *content* is the text accumulated
    so far, attached to the response for convenience.
    """
    usage = chunk.get("usage")
    if not isinstance(usage, dict):
        return None
    return LLMResponse(content=content, usage=MappingProxyType(dict(usage)), raw=chunk)


def _stream_http_error_urllib(exc: urllib.error.HTTPError) -> LLMError:
    """Classify a urllib streaming ``HTTPError`` and return the mapped error.

    Producer threads enqueue the returned exception for the consuming
    coroutine to raise — they cannot raise across the thread boundary directly.
    """
    try:
        raw = _load_json(exc.read())
    except ProviderError:
        raw = {}
    retry_after = _parse_retry_after(
        exc.headers.get("retry-after", "1") if exc.headers else "1"
    )
    return _classify_http_error_return(exc.code, raw, retry_after, cause=exc)


def _classify_http_error_return(
    status: int,
    raw: dict[str, Any],
    retry_after: float,
    *,
    cause: BaseException,
) -> LLMError:
    """Like :func:`_classify_http_error` but returns the error instead of raising."""
    try:
        _classify_http_error(status, raw, retry_after, cause=cause)
    except LLMError as classified:
        return classified
    raise AssertionError("unreachable")  # pragma: no cover


def _raise_httpx_stream_error(resp: Any) -> NoReturn:  # pragma: no cover
    """Classify and raise the error for a failed httpx streaming response."""
    assert _httpx is not None  # noqa: S101
    try:
        raw = resp.json()
        if not isinstance(raw, dict):
            raw = {}
    except (ValueError, UnicodeDecodeError):
        raw = {}
    retry_after = _parse_retry_after(resp.headers.get("retry-after", "1"))
    cause = _httpx.HTTPStatusError(
        "streaming request failed", request=resp.request, response=resp
    )
    _classify_http_error(resp.status_code, raw, retry_after, cause=cause)
