"""Unit coverage for the shared vote-tallying helper (engine/voting.py).

The live consensus pattern and the Message Batches fan-out both dispatch to
``tally_votes`` — these tests pin the voting semantics both transports share.
"""

from __future__ import annotations

import pytest

from executionkit.engine.voting import VoteTally, normalize_response, tally_votes
from executionkit.provider import ConsensusFailedError
from executionkit.types import VotingStrategy


class TestNormalizeResponse:
    def test_collapses_internal_whitespace_and_strips(self) -> None:
        assert normalize_response("  Paris\n\n is  nice ") == "Paris is nice"


class TestTallyVotesMajority:
    def test_most_common_wins_and_ratio_reflects_votes(self) -> None:
        tally = tally_votes(["Paris", "Paris", "London"], VotingStrategy.MAJORITY)
        assert tally == VoteTally(
            winner="Paris",
            agreement_ratio=pytest.approx(2 / 3),  # type: ignore[arg-type]
            unique_responses=2,
            tie_count=1,
        )

    def test_winner_keeps_original_formatting_not_normalized_form(self) -> None:
        # "  Paris " and "Paris" normalize identically; the winner should be
        # the first original occurrence, whitespace intact.
        tally = tally_votes(["  Paris ", "Paris", "Rome"], VotingStrategy.MAJORITY)
        assert tally.winner == "  Paris "

    def test_tie_counts_every_top_scoring_response(self) -> None:
        tally = tally_votes(["a", "b"], VotingStrategy.MAJORITY)
        assert tally.tie_count == 2
        assert tally.agreement_ratio == pytest.approx(0.5)

    def test_empty_contents_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="empty response set"):
            tally_votes([], VotingStrategy.MAJORITY)


class TestTallyVotesUnanimous:
    def test_identical_after_normalization_passes(self) -> None:
        tally = tally_votes(["Paris", " Paris "], VotingStrategy.UNANIMOUS)
        assert tally.agreement_ratio == 1.0
        assert tally.unique_responses == 1

    def test_disagreement_raises_consensus_failed(self) -> None:
        with pytest.raises(ConsensusFailedError, match="2 distinct responses"):
            tally_votes(["Paris", "London"], VotingStrategy.UNANIMOUS)
