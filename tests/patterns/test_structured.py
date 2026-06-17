"""Tests for the structured() pattern.

All tests use MockProvider exclusively — no real API calls are made.
Covers: JSON parsing, fenced-code extraction, repair on failure,
validator-triggered repair, and retry exhaustion.
"""

from __future__ import annotations

from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.patterns.structured import structured
from executionkit.provider import PatternError

# ---------------------------------------------------------------------------
# structured()
# ---------------------------------------------------------------------------


class TestStructuredPattern:
    async def test_structured_returns_parsed_json(self) -> None:

        provider = MockProvider(responses=['{"answer": 42}'])
        result = await structured(provider, "Return an answer")
        assert result.value == {"answer": 42}
        assert result.metadata["parse_attempts"] == 1
        assert result.metadata["repair_attempts"] == 0
        assert result.metadata["validated"] is True

    async def test_structured_repairs_invalid_json(self) -> None:

        provider = MockProvider(responses=["not json", '{"answer": 42}'])
        result = await structured(provider, "Return an answer", max_retries=1)
        assert result.value == {"answer": 42}
        assert result.metadata["parse_attempts"] == 2
        assert result.metadata["repair_attempts"] == 1

    async def test_structured_validator_triggers_repair(self) -> None:

        provider = MockProvider(
            responses=['{"status": "draft"}', '{"status": "ready"}']
        )

        def validator(value: dict[str, Any] | list[Any]) -> str | None:
            if not isinstance(value, dict):
                return "value must be an object"
            if value["status"] != "ready":
                return "status must be ready"
            return None

        result = await structured(
            provider,
            "Return a ready status",
            validator=validator,
            max_retries=1,
        )
        assert result.value == {"status": "ready"}
        assert result.metadata["validated"] is True
        assert result.metadata["repair_attempts"] == 1

    async def test_structured_accepts_fenced_json(self) -> None:

        provider = MockProvider(responses=['```json\n{"answer": 42}\n```'])
        result = await structured(provider, "Return an answer")
        assert result.value == {"answer": 42}

    async def test_structured_raises_after_retries_exhausted(self) -> None:

        provider = MockProvider(responses=["still not json", "still not json"])
        with pytest.raises(PatternError, match="JSON parse failed"):
            await structured(provider, "Return an answer", max_retries=1)
