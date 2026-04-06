"""Balanced-brace JSON extraction from LLM output.

Provides robust extraction that handles markdown fences and raw embedded
JSON, avoiding the greedy-regex problem that captures to the *last* closing
brace in the entire response.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Pattern: ```json ... ``` (non-greedy, captures content inside fences)
_FENCED_JSON_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL)

# Pattern: ``` ... ``` (any code fence containing JSON)
_FENCED_ANY_RE = re.compile(r"```\s*\n?([\{\[].*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | list[Any]:
    """Extract JSON from LLM output using multiple strategies.

    Strategies (in order):
    1. Raw ``json.loads(text.strip())``
    2. Strip markdown fences (e.g. json or generic code fences)
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
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Strip markdown fences
    match = _FENCED_JSON_RE.search(text)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, (dict, list)):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    match = _FENCED_ANY_RE.search(text)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, (dict, list)):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: Balanced-brace extraction
    return _extract_balanced(text)


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
    # Find the first { or [
    obj_start = text.find("{")
    arr_start = text.find("[")

    if obj_start == -1 and arr_start == -1:
        raise ValueError("No JSON object or array found in text")

    # Pick whichever comes first
    if obj_start == -1:
        start = arr_start
    elif arr_start == -1:
        start = obj_start
    else:
        start = min(obj_start, arr_start)

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == "\\" and in_string:
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char in ("{", "["):
            depth += 1
        elif char in ("}", "]"):
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    result = json.loads(candidate)
                    if isinstance(result, (dict, list)):
                        return result
                except (json.JSONDecodeError, ValueError):
                    pass
                raise ValueError("Found balanced braces but content is not valid JSON")

    raise ValueError("Unbalanced braces/brackets in text")
