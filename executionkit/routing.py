"""Provider routing primitives."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from executionkit.provider import LLMProvider
    from executionkit.types import PatternResult


class RoutedPattern(Protocol):
    """Pattern callable accepted by :class:`Router.run`."""

    def __call__(
        self, provider: LLMProvider, prompt: str, **kwargs: Any
    ) -> Awaitable[PatternResult[Any]]: ...


RoutePredicate = Callable[[str, Mapping[str, Any]], bool]


@dataclass(frozen=True, slots=True)
class RouteRule:
    """A named provider selection rule."""

    name: str
    provider: LLMProvider
    predicate: RoutePredicate
    metadata: Mapping[str, Any] = field(default_factory=dict)


class Router:
    """Select a provider by evaluating rules before a pattern call."""

    def __init__(self, *, rules: Sequence[RouteRule], fallback: LLMProvider) -> None:
        self.rules = tuple(rules)
        self.fallback = fallback

    def select(self, prompt: str, **context: Any) -> LLMProvider:
        readonly_context = MappingProxyType(dict(context))
        for rule in self.rules:
            if rule.predicate(prompt, readonly_context):
                return rule.provider
        return self.fallback

    async def run(
        self,
        pattern: RoutedPattern,
        prompt: str,
        *,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> PatternResult[Any]:
        """Select a provider from *context*, then call *pattern* with it.

        Routing inputs are passed explicitly via *context* and forwarded only to
        the route predicates; ``**kwargs`` are forwarded only to *pattern*.
        Keeping the two disjoint stops routing keys (e.g. ``tier``) from leaking
        into the pattern call — which would raise ``TypeError`` for any pattern
        that does not declare them.
        """
        # Drop a stray "prompt" key so it cannot collide with the positional
        # ``prompt`` argument to ``select`` (``select(prompt, prompt=...)`` would
        # raise TypeError). The predicate still receives the real prompt
        # positionally, so nothing is lost.
        route_context = {
            key: value for key, value in (context or {}).items() if key != "prompt"
        }
        provider = self.select(prompt, **route_context)
        return await pattern(provider, prompt, **kwargs)
