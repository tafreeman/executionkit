"""Kit: a session wrapper that holds a provider and tracks cumulative usage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from executionkit.compose import pipe
from executionkit.cost import CostTracker
from executionkit.patterns.consensus import consensus
from executionkit.patterns.react_loop import react_loop
from executionkit.patterns.refine_loop import refine_loop
from executionkit.provider import LLMProvider  # noqa: TC001
from executionkit.types import PatternResult, TokenUsage, Tool

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


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

    async def consensus(self, prompt: str, **kwargs: Any) -> PatternResult[str]:
        """Run the :func:`~executionkit.patterns.consensus.consensus` pattern.

        All keyword arguments are forwarded unchanged to :func:`consensus`.
        """
        result = await consensus(self.provider, prompt, **kwargs)
        self._record(result.cost)
        return result

    async def refine(self, prompt: str, **kwargs: Any) -> PatternResult[str]:
        """Run the :func:`~executionkit.patterns.refine_loop.refine_loop` pattern.

        All keyword arguments are forwarded unchanged to :func:`refine_loop`.
        """
        result = await refine_loop(self.provider, prompt, **kwargs)
        self._record(result.cost)
        return result

    async def react(
        self, prompt: str, tools: Sequence[Tool], **kwargs: Any
    ) -> PatternResult[str]:
        """Run the :func:`~executionkit.patterns.react_loop.react_loop` pattern.

        All keyword arguments are forwarded unchanged to :func:`react_loop`.
        The provider must satisfy :class:`~executionkit.provider.ToolCallingProvider`;
        react_loop will raise :exc:`~executionkit.provider.PatternError` if it does not.
        """
        result = await react_loop(self.provider, prompt, tools, **kwargs)  # type: ignore[arg-type]
        self._record(result.cost)
        return result

    async def pipe(
        self, prompt: str, *steps: Callable[..., Any], **kwargs: Any
    ) -> PatternResult[Any]:
        """Run :func:`~executionkit.compose.pipe` with this Kit's provider.

        All keyword arguments are forwarded unchanged to :func:`pipe`.
        """
        result = await pipe(self.provider, prompt, *steps, **kwargs)
        self._record(result.cost)
        return result
