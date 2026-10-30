"""Property-based tests (Hypothesis) for JSON extraction and vote tallying.

Hypothesis is a dev-only dependency: the runtime package stays
dependency-free (ADR-004) and nothing under ``executionkit/`` imports it.

Every test shares ``PROPERTY_SETTINGS``: ``derandomize=True`` makes the example
sequence a pure function of the test, so CI cannot flake on a lucky seed, and
``database=None`` stops Hypothesis writing a ``.hypothesis`` directory into the
checkout. Example counts are modest on purpose.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from executionkit.engine.json_extraction import extract_json
from executionkit.engine.voting import normalize_response, tally_votes
from executionkit.provider import ConsensusFailedError
from executionkit.types import VotingStrategy

PROPERTY_SETTINGS = settings(
    derandomize=True,
    database=None,
    deadline=None,
    max_examples=200,
)

# Text biased toward the characters extract_json actually branches on, so the
# fence, brace-balancing and string-escape paths are reached far more often
# than uniform random Unicode would reach them.
_STRUCTURAL_ALPHABET = st.sampled_from(list('{}[]"\\:, \n`jsonrtuefalnl0123456789-.'))
_ARBITRARY_TEXT = st.one_of(
    st.text(),
    st.text(alphabet=_STRUCTURAL_ALPHABET, max_size=200),
    st.builds(
        lambda body, tail: f"```json\n{body}\n```{tail}",
        st.text(alphabet=_STRUCTURAL_ALPHABET, max_size=80),
        st.text(max_size=20),
    ),
)

_JSON_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**53), max_value=2**53),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
)
_JSON_VALUES = st.recursive(
    _JSON_SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=8), children, max_size=4),
    ),
    max_leaves=12,
)
_JSON_CONTAINERS = st.one_of(
    st.lists(_JSON_VALUES, max_size=4),
    st.dictionaries(st.text(max_size=8), _JSON_VALUES, max_size=4),
)

# Prose that cannot itself look like JSON or a fence.
_PLAIN_PROSE = st.text(
    alphabet=st.characters(blacklist_characters='{}[]"`', blacklist_categories=("Cs",)),
    max_size=40,
)


class TestExtractJsonProperties:
    @PROPERTY_SETTINGS
    @given(text=_ARBITRARY_TEXT)
    def test_never_raises_anything_but_its_documented_error(self, text: str) -> None:
        """On any input: a dict/list, or ``ValueError`` -- never another exception."""
        try:
            result = extract_json(text)
        except ValueError:
            return
        assert isinstance(result, (dict, list))

    @PROPERTY_SETTINGS
    @given(
        opener=st.sampled_from(["[", '{"a":']),
        depth=st.integers(min_value=1, max_value=20_000),
        closed=st.booleans(),
    )
    def test_deeply_nested_input_raises_only_value_error(
        self, opener: str, depth: int, closed: bool
    ) -> None:
        """Untrusted nesting beyond the parser's recursion limit is a parse failure.

        ``json.loads`` raises ``RecursionError`` (not a ``ValueError``) past
        roughly a thousand levels, so an LLM response that is nothing but
        brackets used to escape ``extract_json`` as the wrong exception type.
        """
        closer = "]" if opener == "[" else "1}"
        text = opener * depth + (closer * depth if closed else "")
        try:
            result = extract_json(text)
        except ValueError:
            return
        assert isinstance(result, (dict, list))

    @PROPERTY_SETTINGS
    @given(value=_JSON_CONTAINERS, prefix=_PLAIN_PROSE, suffix=_PLAIN_PROSE)
    def test_round_trips_json_embedded_in_prose(
        self, value: dict[str, Any] | list[Any], prefix: str, suffix: str
    ) -> None:
        """A serialized container is recovered exactly from surrounding prose."""
        assert extract_json(f"{prefix}{json.dumps(value)}{suffix}") == value

    @PROPERTY_SETTINGS
    @given(value=_JSON_CONTAINERS, prefix=_PLAIN_PROSE)
    def test_round_trips_json_inside_a_fence(
        self, value: dict[str, Any] | list[Any], prefix: str
    ) -> None:
        payload = json.dumps(value)
        assume("```" not in payload)  # a fence inside the payload is out of scope
        assert extract_json(f"{prefix}\n```json\n{payload}\n```\n") == value


# Short alphabet, with whitespace variants, so duplicates and ties are common.
_VOTE = st.sampled_from(["a", "b", "c", " a", "a ", "a  b", "a b", "\tb\n", "c c", ""])
_VOTES = st.lists(_VOTE, min_size=1, max_size=12)


def _first_occurrence_winner(votes: list[str]) -> str:
    """Reference model: highest normalized count, earliest first occurrence wins."""
    normalized = [normalize_response(v) for v in votes]
    top = max(normalized.count(n) for n in normalized)
    return next(n for n in normalized if normalized.count(n) == top)


class TestTallyVotesProperties:
    @PROPERTY_SETTINGS
    @given(votes=_VOTES)
    def test_is_deterministic_for_a_fixed_input_order(self, votes: list[str]) -> None:
        assert tally_votes(votes, VotingStrategy.MAJORITY) == tally_votes(
            list(votes), VotingStrategy.MAJORITY
        )

    @PROPERTY_SETTINGS
    @given(votes=_VOTES, data=st.data())
    def test_winner_is_permutation_invariant_when_there_is_no_tie(
        self, votes: list[str], data: st.DataObject
    ) -> None:
        original = tally_votes(votes, VotingStrategy.MAJORITY)
        assume(original.tie_count == 1)
        shuffled = data.draw(st.permutations(votes))
        permuted = tally_votes(shuffled, VotingStrategy.MAJORITY)
        # Compare normalized: the winner is the raw text of its first occurrence,
        # which may differ in whitespace between orderings of the same votes.
        assert normalize_response(permuted.winner) == normalize_response(
            original.winner
        )
        assert permuted.agreement_ratio == original.agreement_ratio
        assert permuted.unique_responses == original.unique_responses
        assert permuted.tie_count == 1

    @PROPERTY_SETTINGS
    @given(votes=_VOTES)
    def test_ties_break_by_first_occurrence(self, votes: list[str]) -> None:
        tally = tally_votes(votes, VotingStrategy.MAJORITY)
        assert normalize_response(tally.winner) == _first_occurrence_winner(votes)
        assert tally.winner in votes  # the original, un-normalized text

    @PROPERTY_SETTINGS
    @given(votes=_VOTES)
    def test_unanimous_succeeds_exactly_when_all_normalized_votes_match(
        self, votes: list[str]
    ) -> None:
        all_match = len({normalize_response(v) for v in votes}) == 1
        if all_match:
            tally = tally_votes(votes, VotingStrategy.UNANIMOUS)
            assert tally.winner == votes[0]
        else:
            with pytest.raises(ConsensusFailedError):
                tally_votes(votes, VotingStrategy.UNANIMOUS)
