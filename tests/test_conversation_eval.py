"""Tests for the multi-turn ConversationScript eval harness."""

from __future__ import annotations

from typing import TYPE_CHECKING

from executionkit._mock import MockProvider
from executionkit.evals import (
    ConversationScript,
    Turn,
    run_conversation_script,
)
from executionkit.kit import Kit

if TYPE_CHECKING:
    from executionkit.types import PatternResult


# ---------------------------------------------------------------------------
# Passing scripts
# ---------------------------------------------------------------------------


async def test_passing_script_all_turns_pass() -> None:
    """A script whose every check holds reports passed=True with one result/turn."""
    kit = Kit(MockProvider(responses=["one", "two", "three"]))
    script = ConversationScript(
        name="greet",
        turns=(
            Turn(user="first", check=lambda result: result.value == "one"),
            Turn(user="second", check=lambda result: result.value == "two"),
            Turn(user="third", check=lambda result: result.value == "three"),
        ),
    )

    report = await run_conversation_script(script, kit)

    assert report.passed is True
    assert report.total == 3
    assert report.failed_count == 0
    assert [r.name for r in report.results] == ["greet[0]", "greet[1]", "greet[2]"]
    assert all(r.reason == "passed" for r in report.results)


async def test_passing_check_returning_none_passes() -> None:
    """A check that returns None (rather than True) still passes the turn."""

    def check_ok(result: PatternResult[str]) -> None:
        assert result.value == "ok"  # raising would fail the turn, not return
        return None

    kit = Kit(MockProvider(responses=["ok"]))
    script = ConversationScript(name="quiet", turns=(Turn(user="hi", check=check_ok),))

    report = await run_conversation_script(script, kit)

    assert report.passed is True
    assert report.results[0].reason == "passed"


# ---------------------------------------------------------------------------
# Failing checks
# ---------------------------------------------------------------------------


async def test_failing_check_marks_only_that_turn_failed() -> None:
    """A single failing check fails the report and surfaces the reason."""
    kit = Kit(MockProvider(responses=["good", "bad"]))
    script = ConversationScript(
        name="mixed",
        turns=(
            Turn(user="t1", check=lambda result: result.value == "good"),
            Turn(
                user="t2",
                check=lambda result: (
                    None if result.value == "good" else "expected good"
                ),
            ),
        ),
    )

    report = await run_conversation_script(script, kit)

    assert report.passed is False
    assert report.total == 2
    assert report.passed_count == 1
    assert report.failed_count == 1

    failure = report.failures[0]
    assert failure.name == "mixed[1]"
    assert failure.passed is False
    assert failure.reason == "expected good"


async def test_check_returning_false_uses_default_reason() -> None:
    """A bare False verdict fails with the canonical 'check returned False' reason."""
    kit = Kit(MockProvider(responses=["x"]))
    script = ConversationScript(
        name="strict",
        turns=(Turn(user="hi", check=lambda result: False),),
    )

    report = await run_conversation_script(script, kit)

    assert report.passed is False
    assert report.results[0].reason == "check returned False"


# ---------------------------------------------------------------------------
# Conversation state carries across turns
# ---------------------------------------------------------------------------


async def test_context_carries_across_turns() -> None:
    """The second turn's provider call must see the first turn's user message."""
    provider = MockProvider(responses=["reply-1", "reply-2"])
    kit = Kit(provider)
    script = ConversationScript(
        name="ctx",
        turns=(
            Turn(
                user="remember apples",
                check=lambda result: result.value == "reply-1",
            ),
            Turn(user="and bananas", check=lambda result: result.value == "reply-2"),
        ),
    )

    report = await run_conversation_script(script, kit)
    assert report.passed is True

    # Two turns → two provider calls. The last call (turn 2) must include the
    # earlier user turn plus its assistant reply, then the new user turn.
    assert provider.last_call is not None
    last_messages = provider.last_call.messages
    contents = [m.get("content") for m in last_messages]
    assert "remember apples" in contents
    assert "reply-1" in contents
    assert last_messages[-1]["content"] == "and bananas"
    assert [m["role"] for m in last_messages] == ["user", "assistant", "user"]


# ---------------------------------------------------------------------------
# Exceptions become failed results, not raised errors
# ---------------------------------------------------------------------------


async def test_exception_in_check_becomes_failed_result() -> None:
    """An exception raised inside a check is captured as a failed EvalResult."""

    def boom(result: PatternResult[str]) -> bool:
        raise RuntimeError("check exploded")

    kit = Kit(MockProvider(responses=["whatever"]))
    script = ConversationScript(name="boom", turns=(Turn(user="hi", check=boom),))

    report = await run_conversation_script(script, kit)

    assert report.passed is False
    result = report.results[0]
    assert result.passed is False
    assert result.name == "boom[0]"
    assert result.reason == "RuntimeError: check exploded"


async def test_exception_in_turn_becomes_failed_result() -> None:
    """A turn that raises (provider error) is captured, and later turns still run."""
    provider = MockProvider(responses=["only-one"], exception=ValueError("turn failed"))
    kit = Kit(provider)
    script = ConversationScript(
        name="errs",
        turns=(
            Turn(user="first", check=lambda result: True),
            Turn(user="second", check=lambda result: True),
        ),
    )

    report = await run_conversation_script(script, kit)

    assert report.passed is False
    assert report.total == 2
    # Both turns fail because the provider raises on every call.
    assert report.failed_count == 2
    assert report.results[0].name == "errs[0]"
    assert "ValueError: turn failed" in report.results[0].reason
    assert "ValueError: turn failed" in report.results[1].reason
