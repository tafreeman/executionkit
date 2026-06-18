"""Kit: a session wrapper that holds a provider and tracks cumulative usage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from executionkit._constants import DEFAULT_MAX_TOKENS
from executionkit.compose import pipe
from executionkit.cost import CostTracker
from executionkit.engine.messages import user_message
from executionkit.errors import ExecutionKitError
from executionkit.patterns.base import checked_stream
from executionkit.patterns.consensus import consensus
from executionkit.patterns.map_reduce import map_reduce
from executionkit.patterns.react_loop import react_loop
from executionkit.patterns.refine_loop import refine_loop
from executionkit.provider import (
    LLMProvider,
    StreamingProvider,
    ToolCallingProvider,
    _provider_supports_tools,
)
from executionkit.types import (
    PatternResult,
    StreamingPatternResult,
    TokenUsage,
    Tool,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
    from types import TracebackType

    from executionkit.observability import TraceCallback


_STREAM_CONSENSUS_TEMPERATURE = 0.9
_STREAM_REACT_TEMPERATURE = 0.3


class Kit:
    """Session that holds a :class:`~executionkit.provider.Provider` and
    tracks cumulative token usage across all pattern calls.

    Args:
        provider: The LLM provider to use for all calls.
        track_cost: When ``True`` (default), accumulate usage in an internal
            :class:`~executionkit.cost.CostTracker`.  Set to ``False`` to
            disable tracking (e.g. in hot paths or tests).
    """

    def __init__(self, provider: LLMProvider, *, track_cost: bool = True) -> None:
        self.provider = provider
        self._tracker: CostTracker | None = CostTracker() if track_cost else None

    @property
    def usage(self) -> TokenUsage:
        """Cumulative token usage across all calls made through this Kit."""
        return self._tracker.to_usage() if self._tracker is not None else TokenUsage()

    def _record(self, cost: TokenUsage) -> None:
        """Add *cost* to the internal tracker (no-op when tracking disabled)."""
        if self._tracker is not None:
            self._tracker.add_usage(cost)

    async def _run_tracked(
        self, coro: Awaitable[PatternResult[Any]]
    ) -> PatternResult[Any]:
        """Await *coro*, recording its cost on success or failure.

        ExecutionKit pattern errors (e.g. ``BudgetExhaustedError``,
        ``MaxIterationsError``) carry the partial ``cost`` accrued before they
        were raised. Recording it here keeps :attr:`usage` honest even when a
        pattern aborts, instead of silently dropping the spend.
        """
        try:
            result = await coro
        except ExecutionKitError as exc:
            self._record(exc.cost)
            raise
        self._record(result.cost)
        return result

    async def consensus(self, prompt: str, **kwargs: Any) -> PatternResult[str]:
        """Run the :func:`~executionkit.patterns.consensus.consensus` pattern.

        All keyword arguments are forwarded unchanged to :func:`consensus`.
        """
        return await self._run_tracked(consensus(self.provider, prompt, **kwargs))

    async def refine(self, prompt: str, **kwargs: Any) -> PatternResult[str]:
        """Run the :func:`~executionkit.patterns.refine_loop.refine_loop` pattern.

        All keyword arguments are forwarded unchanged to :func:`refine_loop`.
        """
        return await self._run_tracked(refine_loop(self.provider, prompt, **kwargs))

    async def react(
        self, prompt: str, tools: Sequence[Tool], **kwargs: Any
    ) -> PatternResult[str]:
        """Run the :func:`~executionkit.patterns.react_loop.react_loop` pattern.

        All keyword arguments are forwarded unchanged to :func:`react_loop`.
        The provider must satisfy :class:`~executionkit.provider.ToolCallingProvider`;
        a :exc:`TypeError` is raised if it does not.
        """
        provider = self.provider
        if not _provider_supports_tools(provider):
            msg = (
                f"react() requires a ToolCallingProvider; "
                f"{type(provider).__name__} does not support tool calling."
            )
            raise TypeError(msg)
        # _provider_supports_tools verified isinstance + supports_tools=True;
        # cast is safe here because mypy cannot narrow through the helper.
        tool_provider = cast("ToolCallingProvider", provider)
        return await self._run_tracked(
            react_loop(tool_provider, prompt, tools, **kwargs)
        )

    async def map_reduce(
        self, inputs: Sequence[str], **kwargs: Any
    ) -> PatternResult[str]:
        """Run the :func:`~executionkit.patterns.map_reduce.map_reduce` pattern.

        All keyword arguments are forwarded unchanged to :func:`map_reduce`.
        ``map_prompt_template`` and ``reduce_prompt_template`` are required
        keyword arguments.
        """
        return await self._run_tracked(map_reduce(self.provider, inputs, **kwargs))

    async def pipe(
        self, prompt: str, *steps: Callable[..., Any], **kwargs: Any
    ) -> PatternResult[Any]:
        """Run :func:`~executionkit.compose.pipe` with this Kit's provider.

        All keyword arguments are forwarded unchanged to :func:`pipe`.
        """
        return await self._run_tracked(pipe(self.provider, prompt, *steps, **kwargs))

    async def stream_consensus(
        self,
        prompt: str,
        *,
        temperature: float = _STREAM_CONSENSUS_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_cost: TokenUsage | None = None,
        trace: TraceCallback | None = None,
    ) -> StreamingPatternResult:
        """Stream a single live completion of *prompt*.

        Consensus voting needs complete responses to compare, so the full
        pattern has no coherent token stream; this convenience method streams
        **one** generation (no voting).  Token deltas arrive live and
        ``result.cost`` becomes accurate once the stream is drained, at which
        point the spend is folded into this Kit's cumulative :attr:`usage`.
        """
        return await self._stream_single(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            max_cost=max_cost,
            trace=trace,
        )

    async def stream_react_loop(
        self,
        prompt: str,
        tools: Sequence[Tool] = (),
        *,
        temperature: float = _STREAM_REACT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_cost: TokenUsage | None = None,
        trace: TraceCallback | None = None,
    ) -> StreamingPatternResult:
        """Stream a single live model turn for *prompt*.

        The full ReAct loop runs tools across multiple rounds and cannot be
        expressed as one token stream, so this convenience method streams a
        single model generation.  *tools* is accepted for parity with
        :meth:`react` but is **not** executed (tool-call deltas carry no
        message content).  ``result.cost`` is accurate after the stream drains
        and folds into this Kit's :attr:`usage`.
        """
        del tools  # accepted for parity with react(); not executed when streaming
        return await self._stream_single(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            max_cost=max_cost,
            trace=trace,
        )

    async def _stream_single(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        max_cost: TokenUsage | None,
        trace: TraceCallback | None,
    ) -> StreamingPatternResult:
        """Stream one budget-checked generation, folding cost into Kit usage."""
        provider = self.provider
        if not isinstance(provider, StreamingProvider):
            msg = (
                f"streaming requires a StreamingProvider; "
                f"{type(provider).__name__} does not implement stream()."
            )
            raise TypeError(msg)
        local = CostTracker()
        result = await checked_stream(
            provider,
            [user_message(prompt)],
            local,
            max_cost,
            None,
            trace,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        inner = result.text_stream
        metadata = result.metadata

        async def _folded() -> AsyncIterator[str]:
            try:
                async for token in inner:
                    yield token
            finally:
                self._record(local.to_usage())

        return StreamingPatternResult(
            text_stream=_folded(),
            metadata=metadata,
            _usage_source=local.to_usage,
        )

    async def __aenter__(self) -> Kit:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        aclose = getattr(self.provider, "aclose", None)
        if aclose is not None:
            await aclose()
