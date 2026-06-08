"""Golden eval dataset for ExecutionKit patterns.

Exposes ``golden_cases() -> list[EvalCase]`` covering all four patterns
(structured, consensus, refine, react) with deterministic MockProvider
responses so the suite runs offline in CI.
"""

from __future__ import annotations

from typing import Any

from executionkit._mock import MockProvider
from executionkit.evals import EvalCase
from executionkit.provider import LLMResponse, ToolCall
from executionkit.types import PatternResult, Tool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_response(tc_id: str, name: str, args: dict[str, Any]) -> LLMResponse:
    """Return an LLMResponse that represents a single tool-call request."""
    return LLMResponse(
        content="",
        finish_reason="tool_calls",
        tool_calls=(ToolCall(tc_id, name, args),),
    )


def _final_response(content: str) -> LLMResponse:
    """Return an LLMResponse that represents a final (non-tool) answer."""
    return LLMResponse(content=content, finish_reason="stop", tool_calls=())


# ---------------------------------------------------------------------------
# Case builders — one async def per case, fresh provider on every call
# ---------------------------------------------------------------------------


def _case_structured_clean_json() -> EvalCase:
    async def run() -> PatternResult[Any]:
        from executionkit.patterns.structured import structured

        provider = MockProvider(responses=['{"answer": 42}'])
        return await structured(provider, "return json")

    def check(result: PatternResult[Any]) -> str | None:
        if result.value != {"answer": 42}:
            return f"value mismatch: {result.value!r}"
        if result.metadata["parse_attempts"] != 1:
            return f"parse_attempts={result.metadata['parse_attempts']}, want 1"
        if result.metadata["repair_attempts"] != 0:
            return f"repair_attempts={result.metadata['repair_attempts']}, want 0"
        if result.metadata["validated"] is not True:
            return f"validated={result.metadata['validated']!r}, want True"
        return None

    return EvalCase(
        name="structured/clean-json",
        run=run,
        check=check,
        metadata={"category": "structured"},
    )


def _case_structured_json_fenced() -> EvalCase:
    async def run() -> PatternResult[Any]:
        from executionkit.patterns.structured import structured

        provider = MockProvider(
            responses=['```json\n{"name": "alice", "age": 30}\n```']
        )
        return await structured(provider, "return user")

    def check(result: PatternResult[Any]) -> str | None:
        if result.value != {"name": "alice", "age": 30}:
            return f"value mismatch: {result.value!r}"
        if result.metadata["parse_attempts"] != 1:
            return f"parse_attempts={result.metadata['parse_attempts']}, want 1"
        if result.metadata["repair_attempts"] != 0:
            return f"repair_attempts={result.metadata['repair_attempts']}, want 0"
        return None

    return EvalCase(
        name="structured/json-fenced",
        run=run,
        check=check,
        metadata={"category": "structured"},
    )


def _case_structured_json_in_prose() -> EvalCase:
    async def run() -> PatternResult[Any]:
        from executionkit.patterns.structured import structured

        provider = MockProvider(
            responses=[
                'Sure! Here is the data: {"city": "Tokyo", "pop": 14}. Hope that helps.'
            ]
        )
        return await structured(provider, "give city data")

    def check(result: PatternResult[Any]) -> str | None:
        if result.value != {"city": "Tokyo", "pop": 14}:
            return f"value mismatch: {result.value!r}"
        if result.metadata["parse_attempts"] != 1:
            return f"parse_attempts={result.metadata['parse_attempts']}, want 1"
        return None

    return EvalCase(
        name="structured/json-in-prose",
        run=run,
        check=check,
        metadata={"category": "structured"},
    )


def _case_structured_escaped_quotes() -> EvalCase:
    async def run() -> PatternResult[Any]:
        from executionkit.patterns.structured import structured

        # Python string: '{"msg": "say \"hi\""}'
        # JSON text:      {"msg": "say \"hi\""}
        provider = MockProvider(responses=['{"msg": "say \\"hi\\""}'])
        return await structured(provider, "return msg")

    def check(result: PatternResult[Any]) -> str | None:
        expected = {"msg": 'say "hi"'}
        if result.value != expected:
            return f"value mismatch: {result.value!r}, want {expected!r}"
        if result.metadata["parse_attempts"] != 1:
            return f"parse_attempts={result.metadata['parse_attempts']}, want 1"
        return None

    return EvalCase(
        name="structured/escaped-quotes",
        run=run,
        check=check,
        metadata={"category": "structured"},
    )


def _case_structured_repair_after_invalid() -> EvalCase:
    async def run() -> PatternResult[Any]:
        from executionkit.patterns.structured import structured

        provider = MockProvider(responses=["not json at all", '{"fixed": true}'])
        return await structured(provider, "return fixed", max_retries=1)

    def check(result: PatternResult[Any]) -> str | None:
        if result.value != {"fixed": True}:
            return f"value mismatch: {result.value!r}"
        if result.metadata["repair_attempts"] != 1:
            return f"repair_attempts={result.metadata['repair_attempts']}, want 1"
        if result.metadata["parse_attempts"] != 2:
            return f"parse_attempts={result.metadata['parse_attempts']}, want 2"
        if result.metadata["validated"] is not True:
            return f"validated={result.metadata['validated']!r}, want True"
        return None

    return EvalCase(
        name="structured/repair-after-invalid",
        run=run,
        check=check,
        metadata={"category": "structured"},
    )


def _case_consensus_unanimous() -> EvalCase:
    async def run() -> PatternResult[str]:
        from executionkit.patterns.consensus import consensus

        provider = MockProvider(responses=["yes", "yes", "yes"])
        return await consensus(provider, "agree?", num_samples=3)

    def check(result: PatternResult[str]) -> str | None:
        if result.value != "yes":
            return f"value mismatch: {result.value!r}, want 'yes'"
        if result.metadata["agreement_ratio"] != 1.0:
            return f"agreement_ratio={result.metadata['agreement_ratio']}, want 1.0"
        if result.metadata["unique_responses"] != 1:
            return f"unique_responses={result.metadata['unique_responses']}, want 1"
        # Majority strategy: Counter has one entry ("yes", 3); sum(1 for c==3) == 1
        if result.metadata["tie_count"] != 1:
            return f"tie_count={result.metadata['tie_count']}, want 1"
        return None

    return EvalCase(
        name="consensus/unanimous",
        run=run,
        check=check,
        metadata={"category": "consensus"},
    )


def _case_consensus_clear_majority() -> EvalCase:
    async def run() -> PatternResult[str]:
        from executionkit.patterns.consensus import consensus

        provider = MockProvider(responses=["alpha", "alpha", "beta"])
        return await consensus(provider, "choose", num_samples=3)

    def check(result: PatternResult[str]) -> str | None:
        if result.value != "alpha":
            return f"value mismatch: {result.value!r}, want 'alpha'"
        ratio = result.metadata["agreement_ratio"]
        if abs(ratio - 2 / 3) >= 0.001:
            return f"agreement_ratio={ratio}, want ~0.667"
        if result.metadata["unique_responses"] != 2:
            return f"unique_responses={result.metadata['unique_responses']}, want 2"
        # "alpha" has count 2 (top); only one entry at count 2 → tie_count == 1
        if result.metadata["tie_count"] != 1:
            return f"tie_count={result.metadata['tie_count']}, want 1"
        return None

    return EvalCase(
        name="consensus/clear-majority",
        run=run,
        check=check,
        metadata={"category": "consensus"},
    )


def _case_consensus_exact_tie() -> EvalCase:
    async def run() -> PatternResult[str]:
        from executionkit.patterns.consensus import consensus

        provider = MockProvider(responses=["red", "blue"])
        return await consensus(provider, "pick one", num_samples=2)

    def check(result: PatternResult[str]) -> str | None:
        # Both "red" and "blue" get count 1 — two entries share the top count
        if result.metadata["tie_count"] != 2:
            return f"tie_count={result.metadata['tie_count']}, want 2"
        ratio = result.metadata["agreement_ratio"]
        if abs(ratio - 0.5) >= 0.001:
            return f"agreement_ratio={ratio}, want 0.5"
        if result.metadata["unique_responses"] != 2:
            return f"unique_responses={result.metadata['unique_responses']}, want 2"
        # Do NOT assert result.value — winner is implementation-defined on tie
        return None

    return EvalCase(
        name="consensus/exact-tie",
        run=run,
        check=check,
        metadata={"category": "consensus"},
    )


def _case_refine_best_not_last() -> EvalCase:
    async def run() -> PatternResult[str]:
        from executionkit.patterns.refine_loop import refine_loop

        scores: dict[str, float] = {"v1": 0.4, "v2": 0.9, "v3": 0.5}

        async def evaluator(text: str, provider: object) -> float:
            return scores[text]

        provider = MockProvider(responses=["v1", "v2", "v3"])
        # target_score=1.0 ensures no early convergence; max_iterations=2 gives
        # exactly 2 refinement iterations: initial→v1, iter1→v2, iter2→v3
        return await refine_loop(
            provider,
            "improve",
            evaluator=evaluator,
            target_score=1.0,
            max_iterations=2,
        )

    def check(result: PatternResult[str]) -> str | None:
        if result.value != "v2":
            return f"value={result.value!r}, want 'v2' (best, not last)"
        score = result.score
        if score is None or abs(score - 0.9) >= 0.001:
            return f"score={score}, want ~0.9"
        if result.metadata["converged"] is not False:
            return f"converged={result.metadata['converged']!r}, want False"
        history = result.metadata["score_history"]
        if history != [0.4, 0.9, 0.5]:
            return f"score_history={history!r}, want [0.4, 0.9, 0.5]"
        return None

    return EvalCase(
        name="refine/best-not-last",
        run=run,
        check=check,
        metadata={"category": "refine"},
    )


def _case_react_single_tool_call() -> EvalCase:
    async def run() -> PatternResult[str]:
        from executionkit.patterns.react_loop import react_loop

        async def async_lookup(q: str) -> str:
            return f"found:{q}"

        tool = Tool(
            name="lookup",
            description="look up",
            parameters={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
            execute=async_lookup,
        )
        responses = [
            _tool_response("tc1", "lookup", {"q": "hello"}),
            _final_response("The answer is hello"),
        ]
        provider = MockProvider(responses=responses)
        return await react_loop(provider, "find hello", [tool])

    def check(result: PatternResult[str]) -> str | None:
        if result.value != "The answer is hello":
            return f"value={result.value!r}, want 'The answer is hello'"
        if result.metadata["tool_calls_made"] != 1:
            return f"tool_calls_made={result.metadata['tool_calls_made']}, want 1"
        if result.metadata["rounds"] != 2:
            return f"rounds={result.metadata['rounds']}, want 2"
        if result.cost.llm_calls != 2:
            return f"llm_calls={result.cost.llm_calls}, want 2"
        return None

    return EvalCase(
        name="react/single-tool-call",
        run=run,
        check=check,
        metadata={"category": "react"},
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def golden_cases() -> list[EvalCase]:
    """Return all golden eval cases (>= 9) for deterministic offline CI runs."""
    return [
        _case_structured_clean_json(),
        _case_structured_json_fenced(),
        _case_structured_json_in_prose(),
        _case_structured_escaped_quotes(),
        _case_structured_repair_after_invalid(),
        _case_consensus_unanimous(),
        _case_consensus_clear_majority(),
        _case_consensus_exact_tie(),
        _case_refine_best_not_last(),
        _case_react_single_tool_call(),
    ]
