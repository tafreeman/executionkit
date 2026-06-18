"""Tests for the two-tier JSON Schema tool-argument validator (Item A).

Tier A is the always-available, dependency-free subset validator; Tier B uses the
optional ``jsonschema`` package. Per jsonschema's own docs the exact error
*wording* is not public API, so these tests assert pass/fail (return value is
``None`` vs. not ``None``) rather than message text.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from types import MappingProxyType
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.patterns.react_loop import (
    _subset_validate_tool_args,
    _validate_tool_args,
    react_loop,
)
from executionkit.provider import LLMResponse, ToolCall
from executionkit.types import PatternResult, Tool

# ---------------------------------------------------------------------------
# Tier A — subset validator (always available)
# ---------------------------------------------------------------------------


def test_subset_validator_rejects_missing_required() -> None:
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    assert _subset_validate_tool_args(schema, {}) is not None


def test_subset_validator_rejects_extra_field() -> None:
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": [],
        "additionalProperties": False,
    }
    assert _subset_validate_tool_args(schema, {"query": "x", "extra": 1}) is not None


def test_subset_validator_rejects_wrong_top_level_type() -> None:
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": [],
    }
    assert _subset_validate_tool_args(schema, {"count": "not-an-int"}) is not None
    assert _subset_validate_tool_args(schema, {"count": 5}) is None


# ---------------------------------------------------------------------------
# Tier B — jsonschema (skipped when the optional package is absent)
# ---------------------------------------------------------------------------


def test_jsonschema_tier_validates_nested_object() -> None:
    pytest.importorskip("jsonschema")
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        },
        "required": ["user"],
    }
    # Nested required field missing: Tier A passes (user is a dict), Tier B fails.
    assert _validate_tool_args(schema, {"user": {}}) is not None
    assert _validate_tool_args(schema, {"user": {"name": "ada"}}) is None


def test_jsonschema_tier_validates_enum() -> None:
    pytest.importorskip("jsonschema")
    schema = {
        "type": "object",
        "properties": {"color": {"type": "string", "enum": ["red", "green"]}},
        "required": ["color"],
    }
    assert _validate_tool_args(schema, {"color": "blue"}) is not None
    assert _validate_tool_args(schema, {"color": "red"}) is None


def test_jsonschema_tier_validates_minimum_maximum() -> None:
    pytest.importorskip("jsonschema")
    schema = {
        "type": "object",
        "properties": {"age": {"type": "integer", "minimum": 0, "maximum": 120}},
        "required": ["age"],
    }
    assert _validate_tool_args(schema, {"age": 200}) is not None
    assert _validate_tool_args(schema, {"age": -1}) is not None
    assert _validate_tool_args(schema, {"age": 30}) is None


def test_jsonschema_tier_validates_pattern_regex() -> None:
    pytest.importorskip("jsonschema")
    schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "pattern": "^[A-Z]{3}$"}},
        "required": ["code"],
    }
    assert _validate_tool_args(schema, {"code": "abc"}) is not None
    assert _validate_tool_args(schema, {"code": "ABC"}) is None


def test_falls_back_to_tier_a_when_jsonschema_absent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "jsonschema":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    # Reset the one-time notice flag (on the real submodule, not the function the
    # patterns package re-exports under the same name) so the notice fires here.
    react_loop_module = sys.modules["executionkit.patterns.react_loop"]
    monkeypatch.setattr(react_loop_module, "_subset_validator_warned", False)

    schema = {
        "type": "object",
        "properties": {"color": {"type": "string", "enum": ["red", "green"]}},
        "required": ["color"],
    }
    # An enum violation is a Tier-B-only check; with jsonschema "absent" the
    # subset validator lets it through (returns None) and logs the notice once.
    with caplog.at_level(logging.DEBUG, logger="executionkit.patterns.react_loop"):
        assert _validate_tool_args(schema, {"color": "blue"}) is None
    assert any("subset validator" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Integration — invalid args become observations, not exceptions
# ---------------------------------------------------------------------------


async def test_validation_errors_become_observations_not_exceptions() -> None:
    async def _execute(query: str) -> str:
        return "ran"

    tool = Tool(
        name="search",
        description="Search the web",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        execute=_execute,
    )
    invalid_call = LLMResponse(
        content="",
        finish_reason="tool_calls",
        tool_calls=(ToolCall(id="tc1", name="search", arguments={"wrong": "x"}),),
        usage=MappingProxyType({"prompt_tokens": 5, "completion_tokens": 5}),
    )
    final = LLMResponse(
        content="done",
        finish_reason="stop",
        tool_calls=(),
        usage=MappingProxyType({"prompt_tokens": 5, "completion_tokens": 5}),
    )
    provider = MockProvider(responses=[invalid_call, final])

    # Invalid args must not raise — they become an error observation and the
    # loop continues to a final answer.
    result = await react_loop(provider, "go", tools=[tool])
    assert isinstance(result, PatternResult)
    assert result.value == "done"
    assert result.metadata["tool_calls_made"] == 1
