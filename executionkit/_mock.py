"""Mock LLM provider for testing.

``MockProvider`` satisfies the ``LLMProvider`` protocol by returning
pre-configured responses in order, cycling when the list is exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from executionkit.provider import LLMResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence


@dataclass
class _CallRecord:
    """Record of a single call to MockProvider.complete()."""

    messages: list[dict[str, Any]]
    temperature: float | None
    max_tokens: int | None
    tools: list[dict[str, Any]] | None
    kwargs: dict[str, Any]


@dataclass
class MockProvider:
    """Test double implementing ``LLMProvider`` and ``ToolCallingProvider``.

    Accepts a list of responses (strings or ``LLMResponse`` objects) and
    returns them in order, cycling when exhausted.  Optionally raises a
    configured exception to test error paths.
    """

    supports_tools: Literal[True] = field(default=True, init=False)
    responses: list[str | LLMResponse] = field(default_factory=list)
    exception: Exception | None = None
    calls: list[_CallRecord] = field(default_factory=list, init=False)
    _index: int = field(default=0, init=False, repr=False)

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return the next pre-configured response or raise the configured exception."""
        self.calls.append(
            _CallRecord(
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                tools=list(tools) if tools else None,
                kwargs=kwargs,
            )
        )

        if self.exception is not None:
            raise self.exception

        if not self.responses:
            return LLMResponse(content="")

        raw = self.responses[self._index % len(self.responses)]
        self._index += 1

        if isinstance(raw, LLMResponse):
            return raw
        return LLMResponse(content=raw)

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
        """Stream the next canned response one character at a time.

        Mirrors :meth:`complete` accounting (records the call, honours
        ``exception``, cycles the response index) but yields the response
        incrementally.  When *usage_sink* is provided, a final
        :class:`LLMResponse` carrying synthesized token usage is appended so
        streaming callers can record non-zero output tokens after draining.
        """
        self.calls.append(
            _CallRecord(
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                tools=list(tools) if tools else None,
                kwargs={**kwargs, "stream": True},
            )
        )
        return self._stream(usage_sink)

    async def _stream(self, usage_sink: list[LLMResponse] | None) -> AsyncIterator[str]:
        if self.exception is not None:
            raise self.exception
        if not self.responses:
            if usage_sink is not None:
                usage_sink.append(LLMResponse(content=""))
            return
        raw = self.responses[self._index % len(self.responses)]
        self._index += 1
        response = raw if isinstance(raw, LLMResponse) else LLMResponse(content=raw)
        for char in response.content:
            yield char
        if usage_sink is not None:
            usage_sink.append(_mock_stream_response(response))

    @property
    def call_count(self) -> int:
        """Number of calls made so far."""
        return len(self.calls)

    @property
    def last_call(self) -> _CallRecord | None:
        """Most recent call record, or ``None`` if no calls yet."""
        return self.calls[-1] if self.calls else None


def _mock_stream_response(response: LLMResponse) -> LLMResponse:
    """Return *response* if it already carries usage, else synthesize it.

    Streaming callers record token usage after draining, so a mock must report
    non-zero output tokens.  Uses a trivial whitespace word count (min 1 for
    non-empty content) when the canned response has no usage of its own.
    """
    if response.usage:
        return response
    text = response.content
    completion_tokens = max(1, len(text.split())) if text else 0
    return LLMResponse(
        content=text,
        usage=MappingProxyType(
            {"prompt_tokens": 0, "completion_tokens": completion_tokens}
        ),
    )
