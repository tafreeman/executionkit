"""Tests for types.py — TokenUsage, PatternResult, Tool, VotingStrategy, Evaluator."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType
from typing import Any

import pytest

from executionkit.types import (
    Evaluator,
    PatternResult,
    TokenUsage,
    Tool,
    VotingStrategy,
)

# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_default_values_are_zero(self) -> None:
        u = TokenUsage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.llm_calls == 0

    def test_frozen(self) -> None:
        u = TokenUsage(input_tokens=10)
        with pytest.raises(AttributeError):
            u.input_tokens = 99  # type: ignore[misc]

    def test_add_accumulates_fields(self) -> None:
        a = TokenUsage(input_tokens=10, output_tokens=5, llm_calls=1)
        b = TokenUsage(input_tokens=20, output_tokens=8, llm_calls=2)
        c = a + b
        assert c.input_tokens == 30
        assert c.output_tokens == 13
        assert c.llm_calls == 3

    def test_add_returns_new_instance(self) -> None:
        a = TokenUsage(input_tokens=1)
        b = TokenUsage(input_tokens=2)
        c = a + b
        assert c is not a
        assert c is not b

    def test_add_with_zeros(self) -> None:
        a = TokenUsage(input_tokens=5, output_tokens=3, llm_calls=1)
        b = TokenUsage()
        assert a + b == a

    def test_add_identity(self) -> None:
        a = TokenUsage()
        b = TokenUsage()
        assert a + b == TokenUsage()

    def test_equality(self) -> None:
        assert TokenUsage(10, 5, 2) == TokenUsage(10, 5, 2)

    def test_inequality(self) -> None:
        assert TokenUsage(10, 5, 2) != TokenUsage(10, 5, 3)

    def test_token_usage_is_immutable(self) -> None:
        tu = TokenUsage(llm_calls=1)
        with pytest.raises(FrozenInstanceError):
            tu.llm_calls = 2  # type: ignore[misc]

    def test_token_usage_addition_creates_new(self) -> None:
        a = TokenUsage(input_tokens=3, output_tokens=1, llm_calls=1)
        b = TokenUsage(input_tokens=7, output_tokens=2, llm_calls=1)
        c = a + b
        assert c is not a
        assert c is not b
        # Original objects unchanged
        assert a.input_tokens == 3
        assert b.input_tokens == 7


# ---------------------------------------------------------------------------
# PatternResult
# ---------------------------------------------------------------------------


class TestPatternResult:
    def test_frozen(self) -> None:
        r: PatternResult[str] = PatternResult(value="hello")
        with pytest.raises(AttributeError):
            r.value = "other"  # type: ignore[misc]

    def test_pattern_result_is_immutable(self) -> None:
        pr: PatternResult[str] = PatternResult(value="x", cost=TokenUsage())
        with pytest.raises(FrozenInstanceError):
            pr.value = "y"  # type: ignore[misc]

    def test_str_returns_str_of_value(self) -> None:
        r: PatternResult[str] = PatternResult(value="hello")
        assert str(r) == "hello"

    def test_str_with_non_string_value(self) -> None:
        r: PatternResult[int] = PatternResult(value=42)
        assert str(r) == "42"

    def test_score_default_is_none(self) -> None:
        r: PatternResult[str] = PatternResult(value="x")
        assert r.score is None

    def test_cost_default_is_empty_token_usage(self) -> None:
        r: PatternResult[str] = PatternResult(value="x")
        assert r.cost == TokenUsage()

    def test_metadata_default_is_empty_dict(self) -> None:
        r: PatternResult[str] = PatternResult(value="x")
        assert r.metadata == {}

    def test_with_all_fields(self) -> None:
        cost = TokenUsage(input_tokens=10, output_tokens=5, llm_calls=1)
        meta = MappingProxyType({"key": "value"})
        r: PatternResult[str] = PatternResult(
            value="answer",
            score=0.9,
            cost=cost,
            metadata=meta,
        )
        assert r.value == "answer"
        assert r.score == 0.9
        assert r.cost == cost
        assert r.metadata == meta

    def test_pattern_result_metadata_is_immutable(self) -> None:
        r: PatternResult[str] = PatternResult(
            value="x", metadata=MappingProxyType({"k": "v"})
        )
        with pytest.raises(TypeError):
            r.metadata["k"] = "changed"  # type: ignore[index]

    def test_generic_with_dict(self) -> None:
        r: PatternResult[dict[str, Any]] = PatternResult(value={"foo": "bar"})
        assert r.value == {"foo": "bar"}
        assert str(r) == "{'foo': 'bar'}"

    def test_generic_with_int(self) -> None:
        r: PatternResult[int] = PatternResult(value=100)
        assert r.value == 100

    def test_generic_with_list(self) -> None:
        r: PatternResult[list[int]] = PatternResult(value=[1, 2, 3])
        assert r.value == [1, 2, 3]

    def test_equality(self) -> None:
        r1: PatternResult[str] = PatternResult(value="a", score=0.5)
        r2: PatternResult[str] = PatternResult(value="a", score=0.5)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class TestTool:
    def _make_tool(self, name: str = "search") -> Tool:
        async def _execute(query: str) -> str:
            return f"result for {query}"

        return Tool(
            name=name,
            description="Search the web",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=_execute,
        )

    def test_tool_is_frozen(self) -> None:
        tool = self._make_tool()
        with pytest.raises(AttributeError):
            tool.name = "other"  # type: ignore[misc]

    def test_tool_fields(self) -> None:
        tool = self._make_tool("my_search")
        assert tool.name == "my_search"
        assert tool.description == "Search the web"
        assert "query" in tool.parameters["properties"]
        assert tool.timeout == 30.0

    def test_tool_custom_timeout(self) -> None:
        async def _noop() -> str:
            return ""

        tool = Tool(
            name="slow_tool",
            description="A slow tool",
            parameters={},
            execute=_noop,
            timeout=60.0,
        )
        assert tool.timeout == 60.0

    def test_to_schema_structure(self) -> None:
        tool = self._make_tool("calculator")
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert "function" in schema
        fn = schema["function"]
        assert fn["name"] == "calculator"
        assert fn["description"] == "Search the web"
        assert "parameters" in fn

    def test_to_schema_parameters_passthrough(self) -> None:
        params = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        }

        async def _fn(x: int) -> str:
            return str(x)

        tool = Tool(name="fn", description="desc", parameters=params, execute=_fn)
        schema = tool.to_schema()
        assert schema["function"]["parameters"] == params

    async def test_execute_is_async_callable(self) -> None:
        tool = self._make_tool()
        result = await tool.execute(query="hello")
        assert "hello" in result

    def test_parameters_wrapped_in_mapping_proxy(self) -> None:
        """parameters must be a MappingProxyType after construction."""
        tool = self._make_tool()
        assert isinstance(tool.parameters, MappingProxyType)

    def test_parameters_is_read_only(self) -> None:
        """Mutating parameters after construction must raise TypeError."""
        tool = self._make_tool()
        with pytest.raises(TypeError):
            tool.parameters["injected"] = "evil"  # type: ignore[index]

    def test_parameters_already_proxy_not_double_wrapped(self) -> None:
        """Passing a MappingProxyType directly should not double-wrap it."""
        proxy = MappingProxyType({"type": "object"})

        async def _noop() -> str:
            return ""

        tool = Tool(
            name="t",
            description="d",
            parameters=proxy,
            execute=_noop,
        )
        assert tool.parameters is proxy

    def test_to_schema_parameters_is_plain_dict(self) -> None:
        """to_schema() must return a plain dict for parameters (JSON serializable)."""
        import json

        tool = self._make_tool()
        schema = tool.to_schema()
        params = schema["function"]["parameters"]
        assert isinstance(params, dict)
        # Must be JSON-serializable
        json.dumps(params)


# ---------------------------------------------------------------------------
# VotingStrategy
# ---------------------------------------------------------------------------


class TestVotingStrategy:
    def test_majority_value(self) -> None:
        assert VotingStrategy.MAJORITY == "majority"

    def test_unanimous_value(self) -> None:
        assert VotingStrategy.UNANIMOUS == "unanimous"

    def test_is_string_enum(self) -> None:
        assert isinstance(VotingStrategy.MAJORITY, str)
        assert isinstance(VotingStrategy.UNANIMOUS, str)

    def test_from_string_majority(self) -> None:
        v = VotingStrategy("majority")
        assert v is VotingStrategy.MAJORITY

    def test_from_string_unanimous(self) -> None:
        v = VotingStrategy("unanimous")
        assert v is VotingStrategy.UNANIMOUS

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            VotingStrategy("plurality")  # type: ignore[arg-type]

    def test_equality_with_string(self) -> None:
        assert VotingStrategy.MAJORITY == "majority"

    def test_two_members_only(self) -> None:
        members = list(VotingStrategy)
        assert len(members) == 2


# ---------------------------------------------------------------------------
# Evaluator TypeAlias
# ---------------------------------------------------------------------------


class TestEvaluator:
    def test_evaluator_is_importable(self) -> None:
        # Just verify Evaluator can be imported and referenced
        assert Evaluator is not None

    async def test_async_callable_satisfies_evaluator_shape(self) -> None:
        from executionkit._mock import MockProvider

        async def my_evaluator(response: str, provider: MockProvider) -> float:
            return 0.8

        # No runtime isinstance check (TypeAlias can't be used that way),
        # but calling it should work
        result = await my_evaluator("test", MockProvider(responses=["hi"]))
        assert result == 0.8
