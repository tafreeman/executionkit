"""Consensus pattern: parallel sampling with majority or unanimous voting."""

from __future__ import annotations

import collections
import re
from types import MappingProxyType
from typing import Any

from executionkit.cost import CostTracker
from executionkit.engine.messages import user_message
from executionkit.engine.parallel import gather_strict
from executionkit.engine.retry import RetryConfig  # noqa: TC001
from executionkit.patterns.base import checked_complete
from executionkit.provider import ConsensusFailedError, LLMProvider
from executionkit.types import PatternResult, TokenUsage, VotingStrategy


def _normalize(text: str) -> str:
    """Strip and collapse internal whitespace for voting comparison."""
    return re.sub(r"\s+", " ", text.strip())


async def consensus(
    provider: LLMProvider,
    prompt: str,
    *,
    num_samples: int = 5,
    strategy: VotingStrategy | str = "majority",
    temperature: float = 0.9,
    max_tokens: int = 4096,
    max_concurrency: int = 5,
    retry: RetryConfig | None = None,
    max_cost: TokenUsage | None = None,
) -> PatternResult[str]:
    """Run parallel LLM samples and aggregate via voting.

    Fires ``num_samples`` concurrent completions and applies the chosen
    voting strategy to determine the winning response.

    Args:
        provider: LLM provider to call.
        prompt: User prompt sent identically to every sample.
        num_samples: Number of parallel completions to request. Must be >= 1.
        strategy: ``"majority"`` (most common wins) or ``"unanimous"``
            (all must agree).  Accepts a :class:`VotingStrategy` enum or
            a plain string.
        temperature: Sampling temperature (higher = more diverse).
        max_tokens: Maximum tokens per completion.
        max_concurrency: Semaphore limit for parallel calls.
        retry: Optional retry configuration per call.
        max_cost: Optional token/call budget. Passed to each individual
            ``checked_complete`` call. ``None`` means unlimited.

    Returns:
        A :class:`PatternResult` whose ``value`` is the winning response,
        ``score`` is the agreement ratio, and ``metadata`` includes
        ``agreement_ratio``, ``unique_responses``, and ``tie_count``.

    Raises:
        ConsensusFailedError: When ``strategy="unanimous"`` and responses
            are not all identical.
        ValueError: If ``num_samples`` is less than 1.

    Metadata:
        agreement_ratio (float): Fraction of samples matching the winner (0.0-1.0).
        unique_responses (int): Number of distinct response strings observed.
        tie_count (int): Number of responses that tied for the top vote count.
    """
    if num_samples < 1:
        raise ValueError(f"num_samples must be >= 1, got {num_samples}")
    if max_concurrency < 1:
        raise ValueError(f"max_concurrency must be >= 1, got {max_concurrency}")
    if max_tokens < 1:
        raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")

    if isinstance(strategy, str):
        strategy = VotingStrategy(strategy)

    tracker = CostTracker()
    messages: list[dict[str, Any]] = [user_message(prompt)]

    coros = [
        checked_complete(
            provider,
            messages,
            tracker,
            budget=max_cost,
            retry=retry,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        for _ in range(num_samples)
    ]

    responses = await gather_strict(coros, max_concurrency=max_concurrency)
    contents = [r.content for r in responses]
    normalized = [_normalize(c) for c in contents]

    counter: collections.Counter[str] = collections.Counter(normalized)

    if strategy == VotingStrategy.UNANIMOUS:
        if len(counter) != 1:
            raise ConsensusFailedError(
                f"Unanimous consensus failed: {len(counter)} distinct responses "
                f"from {num_samples} samples"
            )
        winner = contents[0]
        agreement_ratio = 1.0
        tie_count = 0
    else:
        # MAJORITY: pick the most common response
        most_common = counter.most_common()
        top_count = most_common[0][1]
        tie_count = sum(1 for _, count in most_common if count == top_count)
        winner_normalized = most_common[0][0]
        winner_idx = normalized.index(winner_normalized)
        winner = contents[winner_idx]
        agreement_ratio = top_count / num_samples

    return PatternResult[str](
        value=winner,
        score=agreement_ratio,
        cost=tracker.to_usage(),
        metadata=MappingProxyType(
            {
                "agreement_ratio": agreement_ratio,
                "unique_responses": len(counter),
                "tie_count": tie_count,
            }
        ),
    )
