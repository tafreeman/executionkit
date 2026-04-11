"""LLM provider, response types, and error hierarchy.

Implements a single ``Provider`` class that speaks the OpenAI-compatible
``/chat/completions`` JSON format over stdlib ``urllib``.  Also defines the
``LLMProvider`` structural protocol, frozen value types (``LLMResponse``,
``ToolCall``), and the full 9-class error tree.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, NoReturn, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence
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


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A single tool invocation extracted from an LLM response."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Parsed LLM completion response.

    Handles both OpenAI (``prompt_tokens`` / ``completion_tokens``) and
    Anthropic (``input_tokens`` / ``output_tokens``) usage key formats.
    """

    content: str
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    finish_reason: str = "stop"
    usage: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    raw: Any = None

    @property
    def input_tokens(self) -> int:
        u = self.usage
        if "input_tokens" in u:
            return int(u["input_tokens"])
        return int(u.get("prompt_tokens", 0))

    @property
    def output_tokens(self) -> int:
        u = self.usage
        if "output_tokens" in u:
            return int(u["output_tokens"])
        return int(u.get("completion_tokens", 0))

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
    # Hardcoding True in a wrapper causes isinstance(wrapper, ToolCallingProvider)
    # to return True even when the inner provider cannot handle tools.
    # Ref: PEP 544 runtime_checkable only checks presence, not value.
    supports_tools: Literal[True] = field(default=True, init=False)
    # Derived state — excluded from repr/eq/hash; initialized only in __post_init__
    _client: Any = field(
        default=None, init=False, repr=False, compare=False, hash=False
    )
    _use_httpx: bool = field(
        default=False, init=False, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        # object.__setattr__ is the standard pattern for derived state on frozen
        # dataclasses
        if _HTTPX_AVAILABLE and _httpx is not None:
            object.__setattr__(
                self, "_client", _httpx.AsyncClient(timeout=self.timeout)
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
        data = await self._post("chat/completions", payload)
        return self._parse_response(data)

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Route to the appropriate HTTP backend."""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        body = json.dumps(payload).encode()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self._use_httpx:
            return await self._post_httpx(url, body, headers)
        return await self._post_urllib(url, body, headers)

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
            retry_after = float(exc.response.headers.get("retry-after", "1"))
            _classify_http_error(status, raw, retry_after, cause=exc)
        except _httpx.TransportError as exc:
            raise ProviderError(f"Transport failure: {exc}") from exc

    async def _post_urllib(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """HTTP POST via stdlib ``urllib`` in a thread.

        Maps HTTP errors to the appropriate error class:
        - 429 -> RateLimitError
        - 401 -> PermanentError
        - >=400 -> ProviderError
        """
        request_timeout = self.timeout

        def _sync() -> dict[str, Any]:
            req = urllib.request.Request(  # noqa: S310
                url, data=body, headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=request_timeout) as resp:  # noqa: S310
                    raw: dict[str, Any] = json.loads(resp.read())
                    return raw
            except urllib.error.HTTPError as exc:
                try:
                    raw = _load_json(exc.read())
                except ProviderError:
                    raw = {}
                status = exc.code
                retry_after = float(
                    exc.headers.get("retry-after", "1") if exc.headers else 1
                )
                _classify_http_error(status, raw, retry_after, cause=exc)
            except urllib.error.URLError as exc:
                raise ProviderError(f"Transport failure: {exc.reason}") from exc

        return await asyncio.to_thread(_sync)

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


def _extract_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict):
                    value = text.get("value")
                    if isinstance(value, str):
                        parts.append(value)
            elif isinstance(item.get("value"), str):
                parts.append(str(item["value"]))
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
            f"tool_call arguments were not valid JSON: {arguments}"
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

    Matches tokens that begin with a known prefix (``sk``, ``key``, ``token``,
    ``secret``, ``bearer``, ``auth``) followed by at least 4 non-whitespace,
    non-quote characters — a common shape for API keys and bearer tokens.
    """
    return re.sub(
        r'(?i)(sk|key|token|secret|bearer|auth)[^\s\'"]{4,}',
        "[REDACTED]",
        text,
    )


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
        PermanentError: For HTTP 401, 403, 404.
        ProviderError: For all other non-2xx status codes.
    """
    if status == 429:
        raise RateLimitError(
            "Rate limited (HTTP 429)",
            retry_after=retry_after,
        ) from cause
    if status in {401, 403, 404}:
        raise PermanentError(_format_http_error(status, raw)) from cause
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
