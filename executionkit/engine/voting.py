"""Pure vote-tallying shared by the live consensus pattern and the batch path.

Extracted from :mod:`executionkit.patterns.consensus` so the Anthropic
Message Batches fan-out (:mod:`executionkit.batches`) applies *exactly* the
same voting semantics as the live pattern — one implementation, no drift
between the two transports.
"""

from __future__ import annotations

import collections
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from executionkit.errors import ConsensusFailedError
from executionkit.types import VotingStrategy

if TYPE_CHECKING:
    from collections.abc import Sequence


def normalize_response(text: str) -> str:
    """Strip and collapse internal whitespace for voting comparison."""
    return re.sub(r"\s+", " ", text.strip())


@dataclass(frozen=True, slots=True)
class VoteTally:
    """Outcome of tallying a set of responses under a voting strategy.

    ``winner`` is the original (un-normalized) text of the winning response;
    normalization is applied only for comparison.
    """

    winner: str
    agreement_ratio: float
    unique_responses: int
    tie_count: int


def tally_votes(contents: Sequence[str], strategy: VotingStrategy) -> VoteTally:
    """Apply *strategy* to *contents* and return the winning response.

    Args:
        contents: The raw response texts, one per sample. Must be non-empty.
        strategy: ``VotingStrategy.MAJORITY`` (most common normalized response
            wins; first occurrence breaks ties) or ``VotingStrategy.UNANIMOUS``
            (every normalized response must be identical).

    Raises:
        ValueError: If ``contents`` is empty.
        ConsensusFailedError: When ``strategy`` is unanimous and the responses
            are not all identical after normalization.
    """
    if not contents:
        raise ValueError("cannot tally votes over an empty response set")

    normalized = [normalize_response(content) for content in contents]
    counter: collections.Counter[str] = collections.Counter(normalized)

    if strategy == VotingStrategy.UNANIMOUS:
        if len(counter) != 1:
            raise ConsensusFailedError(
                f"Unanimous consensus failed: {len(counter)} distinct responses "
                f"from {len(contents)} samples"
            )
        return VoteTally(
            winner=contents[0],
            agreement_ratio=1.0,
            unique_responses=1,
            tie_count=0,
        )

    # MAJORITY: pick the most common response
    most_common = counter.most_common()
    top_count = most_common[0][1]
    tie_count = sum(1 for _, count in most_common if count == top_count)
    winner_normalized = most_common[0][0]
    winner = contents[normalized.index(winner_normalized)]
    return VoteTally(
        winner=winner,
        agreement_ratio=top_count / len(contents),
        unique_responses=len(counter),
        tie_count=tie_count,
    )
