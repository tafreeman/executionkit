"""Golden and live eval tests for ExecutionKit."""

from __future__ import annotations

import os
from typing import Any

import pytest

from executionkit._mock import MockProvider
from executionkit.provider import LLMResponse, Provider, ToolCall
from executionkit.types import PatternResult, Tool


async def test_run_eval_suite_reports_pass_and_failure() -> None:
    from executionkit.evals import EvalCase, run_eval_suite

    report = await run_eval_suite(
        [
            EvalCase(
                name="passing",
                run=lambda: "ok",
                check=lambda value: value == "ok",
            ),
            EvalCase(
                name="failing",
                run=lambda: "bad",
                check=lambda value: "expected ok" if value != "ok" else None,
            ),
        ]
    )

    assert report.passed is False
    assert report.total == 2
    assert report.passed_count == 1
    assert report.failed_count == 1
    assert report.failures[0].name == "failing"
    assert report.failures[0].reason == "expected ok"


async def test_deterministic_pattern_goldens_pass() -> None:
    from executionkit.evals import EvalCase, run_eval_suite
    from executionkit.patterns.consensus import consensus
    from executionkit.patterns.react_loop import react_loop
    from executionkit.patterns.refine_loop import refine_loop
    from executionkit.patterns.structured import structured

    async def consensus_golden() -> PatternResult[str]:
        return await consensus(
            MockProvider(responses=["alpha", "alpha", "beta"]),
            "choose",
            num_samples=3,
        )

    async def structured_golden() -> PatternResult[Any]:
        return await structured(
            MockProvider(responses=['{"answer": 42}']),
            "return json",
        )

    async def refine_golden() -> PatternResult[str]:
        scores = {"draft": 0.4, "better": 0.9}

        async def evaluator(value: str, provider: object) -> float:
            return scores[value]

        return await refine_loop(
            MockProvider(responses=["draft", "better"]),
            "improve",
            evaluator=evaluator,
            target_score=0.9,
            max_iterations=2,
        )

    async def react_golden() -> PatternResult[str]:
        async def execute_search(query: str) -> str:
            return f"found:{query}"

        tool = Tool(
            name="search",
            description="search",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=execute_search,
        )
        tool_call = LLMResponse(
            content="",
            tool_calls=(ToolCall("tc1", "search", {"query": "x"}),),
        )
        final = LLMResponse(content="done")
        return await react_loop(
            MockProvider(responses=[tool_call, final]), "find", [tool]
        )

    report = await run_eval_suite(
        [
            EvalCase(
                name="consensus-majority",
                run=consensus_golden,
                check=lambda result: (
                    result.value == "alpha"
                    and result.metadata["agreement_ratio"] == pytest.approx(2 / 3)
                ),
            ),
            EvalCase(
                name="structured-json",
                run=structured_golden,
                check=lambda result: result.value == {"answer": 42},
            ),
            EvalCase(
                name="refine-best",
                run=refine_golden,
                check=lambda result: (
                    result.value == "better" and result.score == pytest.approx(0.9)
                ),
            ),
            EvalCase(
                name="react-tool",
                run=react_golden,
                check=lambda result: (
                    result.value == "done" and result.metadata["tool_calls_made"] == 1
                ),
            ),
        ]
    )

    assert report.passed is True
    assert report.failed_count == 0


def test_live_provider_from_env_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from executionkit.evals import live_provider_from_env

    monkeypatch.delenv("EXECUTIONKIT_LIVE_EVAL", raising=False)

    assert live_provider_from_env() is None


def test_live_provider_from_env_requires_endpoint_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from executionkit.evals import live_provider_from_env

    monkeypatch.setenv("EXECUTIONKIT_LIVE_EVAL", "1")
    monkeypatch.delenv("EXECUTIONKIT_BASE_URL", raising=False)
    monkeypatch.delenv("EXECUTIONKIT_MODEL", raising=False)

    with pytest.raises(ValueError, match="EXECUTIONKIT_BASE_URL"):
        live_provider_from_env()


def test_live_provider_from_env_builds_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from executionkit.evals import live_provider_from_env

    monkeypatch.setenv("EXECUTIONKIT_LIVE_EVAL", "1")
    monkeypatch.setenv("EXECUTIONKIT_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("EXECUTIONKIT_MODEL", "llama3.2")
    monkeypatch.setenv("EXECUTIONKIT_API_KEY", "local")

    provider = live_provider_from_env()

    assert isinstance(provider, Provider)
    assert provider.base_url == "http://localhost:11434/v1"
    assert provider.model == "llama3.2"


@pytest.mark.skipif(
    os.getenv("EXECUTIONKIT_LIVE_EVAL") != "1",
    reason="set EXECUTIONKIT_LIVE_EVAL=1 to run live endpoint evals",
)
async def test_live_structured_endpoint_eval() -> None:
    from executionkit.evals import live_provider_from_env
    from executionkit.patterns.structured import structured

    provider = live_provider_from_env()
    if provider is None:
        pytest.skip("live eval disabled")

    result = await structured(
        provider,
        'Return only JSON with this exact shape: {"answer": 42}',
        max_retries=1,
        temperature=0.0,
        max_tokens=64,
    )

    assert result.value == {"answer": 42}
