"""Balanced-brace JSON extraction from LLM output.

Provides robust extraction that handles markdown fences and raw embedded
JSON, avoiding the greedy-regex problem that captures to the *last* closing
brace in the entire response.
"""

from __future__ import annotations

import json
from typing import Any

_JSON_FENCE = "```json"
_FENCE = "```"


def extract_json(text: str) -> dict[str, Any] | list[Any]:
    """Extract JSON from LLM output using multiple strategies.

    Strategies (in order):
    1. Raw ``json.loads(text.strip())``
    2. Markdown code fences -- the first ```json fence, then the first generic
       fence whose body looks like JSON. Located with ``str.find`` so an
       unterminated fence in untrusted input degrades to a linear scan instead
       of the polynomial backtracking a ``.*?`` regex would incur under DOTALL.
    3. Balanced-brace extraction -- find first ``{`` or ``[``, track nesting
       depth respecting string boundaries, find matching closer.

    Args:
        text: Raw LLM response text that may contain JSON.

    Returns:
        Parsed JSON as a dict or list.

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    # Strategy 1: Try raw json.loads
    stripped = text.strip()
    try:
        result = json.loads(stripped)
        if isinstance(result, (dict, list)):
            return result
    except ValueError:
        pass

    # Strategy 2: Markdown code fences (linear scan, no regex backtracking)
    for candidate in _fenced_candidates(text):
        try:
            result = json.loads(candidate)
            if isinstance(result, (dict, list)):
                return result
        except ValueError:
            continue

    # Strategy 3: Balanced-brace extraction
    return _extract_balanced(text)


def _fenced_candidates(text: str) -> list[str]:
    """Return JSON payloads enclosed in markdown code fences, in priority order.

    Uses ``str.find`` rather than a regular expression: an unterminated fence in
    untrusted input degrades to a single linear scan instead of triggering the
    polynomial backtracking a non-greedy ``.*?`` pattern incurs under DOTALL.

    Order:
    1. the first ``json fence, then
    2. the first generic fence whose body starts with ``{`` or ``[``.
    """
    candidates: list[str] = []

    # 1. First explicit ```json fence.
    start = text.find(_JSON_FENCE)
    if start != -1:
        body_start = start + len(_JSON_FENCE)
        close = text.find(_FENCE, body_start)
        if close != -1:
            candidates.append(text[body_start:close].strip())

    # 2. First generic fence whose body looks like JSON.
    search = 0
    while (open_idx := text.find(_FENCE, search)) != -1:
        body_start = open_idx + len(_FENCE)
        close = text.find(_FENCE, body_start)
        if close == -1:
            break
        body = text[body_start:close].strip()
        if body[:1] in ("{", "["):
            candidates.append(body)
            break
        search = close + len(_FENCE)

    return candidates


def _first_opener(text: str) -> int:
    """Return the index of the first ``{`` or ``[`` in *text*.

    Args:
        text: Raw text to search.

    Returns:
        Index of the first opener character.

    Raises:
        ValueError: If neither ``{`` nor ``[`` appears in *text*.
    """
    obj_start = text.find("{")
    arr_start = text.find("[")

    if obj_start == -1 and arr_start == -1:
        raise ValueError("No JSON object or array found in text")

    if obj_start == -1:
        return arr_start
    if arr_start == -1:
        return obj_start
    return min(obj_start, arr_start)


def _next_char_state(
    char: str,
    in_string: bool,
    escape_next: bool,
) -> tuple[bool, bool, int]:
    """Compute the next string-tracking state and depth delta for one character.

    Returns ``(new_in_string, new_escape_next, depth_delta)`` where
    *depth_delta* is ``+1`` for an opener, ``-1`` for a closer, and ``0``
    otherwise.  The caller is responsible for ignoring characters when
    *escape_next* was ``True`` before this call.

    Args:
        char: The current character being processed.
        in_string: Whether we are currently inside a JSON string.
        escape_next: Whether the previous character was an unescaped backslash.

    Returns:
        A 3-tuple of ``(new_in_string, new_escape_next, depth_delta)``.
    """
    if escape_next:
        return in_string, False, 0

    if char == "\\" and in_string:
        return in_string, True, 0

    if char == '"':
        return not in_string, False, 0

    if in_string:
        return in_string, False, 0

    if char in ("{", "["):
        return in_string, False, 1

    if char in ("}", "]"):
        return in_string, False, -1

    return in_string, False, 0


def _parse_balanced_candidate(candidate: str) -> dict[str, Any] | list[Any]:
    """Parse *candidate* as JSON or raise ``ValueError``.

    Args:
        candidate: A substring that spans a balanced pair of braces/brackets.

    Returns:
        Parsed JSON dict or list.

    Raises:
        ValueError: If *candidate* is not valid JSON or not a dict/list.
    """
    try:
        result = json.loads(candidate)
        if isinstance(result, (dict, list)):
            return result
    except ValueError:
        pass
    raise ValueError("Found balanced braces but content is not valid JSON")


def _extract_balanced(text: str) -> dict[str, Any] | list[Any]:
    """Find the first ``{`` or ``[`` and extract its balanced JSON substring.

    Tracks string boundaries (including escaped quotes) and nesting depth
    to find the correct matching closer.  Both ``{}`` and ``[]`` contribute
    to depth tracking so that nested structures are handled correctly.

    Args:
        text: Raw text containing embedded JSON.

    Returns:
        Parsed JSON dict or list.

    Raises:
        ValueError: If no opener is found or braces/brackets are unbalanced.
    """
    start = _first_opener(text)

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        in_string, escape_next, depth_delta = _next_char_state(
            text[i], in_string, escape_next
        )
        depth += depth_delta
        if depth_delta == -1 and depth == 0:
            return _parse_balanced_candidate(text[start : i + 1])

    raise ValueError("Unbalanced braces/brackets in text")
