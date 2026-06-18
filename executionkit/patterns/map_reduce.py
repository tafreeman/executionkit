"""Map-reduce pattern: fan-out completions over many inputs, then reduce.

:func:`map_reduce` maps a prompt template over an iterable of inputs by
running all completions concurrently (bounded by ``max_concurrency``), then
calls a second reduce prompt to combine the mapped results into a single
final answer.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from executionkit._constants import DEFAULT_MAX_CONCURRENCY, DEFAULT_MAX_TOKENS
from executionkit.cost import CostTracker
from executionkit.engine.messages import user_message
from executionkit.engine.parallel import gather_strict
from executionkit.engine.retry import RetryConfig  # noqa: TC001
from executionkit.patterns.base import checked_complete
from executionkit.provider import LLMProvider  # noqa: TC001
from executionkit.types import PatternResult, TokenUsage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from executionkit.observability import TraceCallback

# Default separator used to join mapped outputs before the reduce prompt.
_DEFAULT_SEPARATOR = "\n\n---\n\n"

# Default sampling temperature for map and reduce calls.
_DEFAULT_TEMPERATURE: float = 0.3


def _build_map_prompt(template: str, item: str) -> str:
    """Substitute ``{item}`` placeholder in *template* with *item*.

    Args:
        template: Prompt template containing the literal ``{item}`` token.
        item: The input value to substitute.

    Returns:
        The rendered prompt string.

    Raises:
        ValueError: If *template* does not contain the ``{item}`` placeholder.
    """
    if "{item}" not in template:
        raise ValueError(
            "map_prompt_template must contain the '{item}' placeholder; "
            f"got: {template!r}"
        )
    return template.replace("{item}", item)


def _build_reduce_prompt(template: str, mapped_outputs: list[str]) -> str:
    """Substitute ``{mapped_outputs}`` placeholder in *template*.

    The mapped results are joined with ``_DEFAULT_SEPARATOR`` before
    substitution.

    Args:
        template: Prompt template containing the literal ``{mapped_outputs}`` token.
        mapped_outputs: List of strings returned by the map phase.

    Returns:
        The rendered reduce prompt string.

    Raises:
        ValueError: If *template* does not contain ``{mapped_outputs}``.
    """
    if "{mapped_outputs}" not in template:
        raise ValueError(
            "reduce_prompt_template must contain the '{mapped_outputs}' placeholder; "
            f"got: {template!r}"
        )
    joined = _DEFAULT_SEPARATOR.join(mapped_outputs)
    return template.replace("{mapped_outputs}", joined)


async def map_reduce(
    provider: LLMProvider,
    inputs: Sequence[str],
    *,
    map_prompt_template: str,
    reduce_prompt_template: str,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
    trace: TraceCallback | None = None,
) -> PatternResult[str]:
    """Fan-out completions over *inputs* concurrently, then reduce.

    **Map phase**: for each item in *inputs*, ``map_prompt_template`` is
    rendered (``{item}`` replaced by the item) and sent to the provider.
    All map calls run concurrently up to ``max_concurrency``.

    **Reduce phase**: all map outputs are joined with a separator and
    substituted into ``reduce_prompt_template`` (``{mapped_outputs}``
    placeholder).  A single reduce call produces the final answer.

    An empty *inputs* sequence skips the map phase entirely and calls the
    reduce step with an empty string substituted for ``{mapped_outputs}``.

    Args:
        provider: LLM provider to call.
        inputs: Items to map over.  Each is substituted into
            ``map_prompt_template`` at ``{item}``.
        map_prompt_template: Prompt template with an ``{item}`` placeholder.
        reduce_prompt_template: Prompt template with a ``{mapped_outputs}``
            placeholder, which is replaced by the joined map results.
        max_concurrency: Maximum simultaneous map calls.  Must be >= 1.
        temperature: Sampling temperature for both map and reduce calls.
        max_tokens: Maximum tokens per completion.
        max_cost: Optional token/call budget shared across all calls.
        retry: Optional retry configuration per call.
        trace: Optional structured trace callback.

    Returns:
        A :class:`~executionkit.types.PatternResult` whose ``value`` is
        the reduce completion, ``score`` is ``None``, and ``metadata``
        includes ``map_count``, ``reduce_calls``, and ``total_calls``.

    Raises:
        ValueError: If ``max_concurrency < 1``, ``max_tokens < 1``, or
            either template is missing its placeholder.
        BudgetExhaustedError: If ``max_cost`` is exceeded during map or
            reduce.

    Metadata:
        map_count (int): Number of items mapped (length of *inputs*).
        reduce_calls (int): Always 1 when *inputs* is non-empty; 0 when
            *inputs* is empty and the reduce prompt contained no outputs
            to combine (still runs one reduce call — ``reduce_calls=1``).
        total_calls (int): Total LLM calls made (``map_count + 1``).
    """
    if max_concurrency < 1:
        raise ValueError(f"max_concurrency must be >= 1, got {max_concurrency}")
    if max_tokens < 1:
        raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")

    tracker = CostTracker()

    # -----------------------------------------------------------------
    # Map phase
    # -----------------------------------------------------------------
    map_count = len(inputs)
    mapped_outputs: list[str]

    if map_count == 0:
        mapped_outputs = []
    else:
        map_coros = [
            checked_complete(
                provider,
                [user_message(_build_map_prompt(map_prompt_template, item))],
                tracker,
                budget=max_cost,
                retry=retry,
                trace=trace,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for item in inputs
        ]
        map_responses = await gather_strict(map_coros, max_concurrency=max_concurrency)
        mapped_outputs = [r.content for r in map_responses]

    # -----------------------------------------------------------------
    # Reduce phase
    # -----------------------------------------------------------------
    reduce_prompt = _build_reduce_prompt(reduce_prompt_template, mapped_outputs)
    reduce_response = await checked_complete(
        provider,
        [user_message(reduce_prompt)],
        tracker,
        budget=max_cost,
        retry=retry,
        trace=trace,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    total_calls = tracker.to_usage().llm_calls
    return PatternResult[str](
        value=reduce_response.content,
        score=None,
        cost=tracker.to_usage(),
        metadata=MappingProxyType(
            {
                "map_count": map_count,
                "reduce_calls": 1,
                "total_calls": total_calls,
            }
        ),
    )
