---
name: add-pattern
description: Step-by-step guide for adding a new LLM reasoning pattern to ExecutionKit
---

## Step 1 — Design the pattern interface

Answer these before writing code:

- **Provider type:** Does the pattern need tool-calling? Use `ToolCallingProvider`. Otherwise use `LLMProvider`.
- **Return type:** What does `PatternResult[T]` wrap? (`str` for text, `dict` for structured, etc.)
- **Key parameters:** What knobs does the caller need? (e.g., `max_iterations`, `temperature`)
- **Metadata keys:** What goes in `result.metadata`? Document every key.

## Step 2 — Create the pattern file

Create `executionkit/patterns/my_pattern.py`. Minimal template:

```python
"""One-line description of the pattern."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from executionkit.cost import CostTracker
from executionkit.engine.messages import user_message
from executionkit.engine.retry import RetryConfig  # noqa: TC001
from executionkit.patterns.base import checked_complete
from executionkit.provider import LLMProvider  # noqa: TC001
from executionkit.types import PatternResult, TokenUsage

if TYPE_CHECKING:
    from executionkit.observability import TraceCallback


async def my_pattern(
    provider: LLMProvider,
    prompt: str,
    *,
    max_tokens: int = 4096,
    retry: RetryConfig | None = None,
    max_cost: TokenUsage | None = None,
    trace: TraceCallback | None = None,
) -> PatternResult[str]:
    """Short description.

    Args:
        provider: LLM provider to call.
        prompt: User prompt.
        max_tokens: Maximum tokens per completion.
        retry: Optional retry configuration.
        max_cost: Optional token/call budget.
        trace: Optional structured trace callback.

    Returns:
        PatternResult whose ``value`` is ... and ``metadata`` includes ...

    Metadata:
        key_name (type): description.
    """
    tracker = CostTracker()
    messages: list[dict[str, Any]] = [user_message(prompt)]

    response = await checked_complete(
        provider,
        messages,
        tracker,
        budget=max_cost,
        retry=retry,
        trace=trace,
        max_tokens=max_tokens,
    )

    return PatternResult[str](
        value=response.content,
        score=None,
        cost=tracker.to_usage(),
        metadata=MappingProxyType({}),
    )
```

## Step 3 — Update `executionkit/patterns/__init__.py`

Add the import and update `__all__`:

```python
from executionkit.patterns.my_pattern import my_pattern

__all__: list[str] = [..., "my_pattern"]
```

## Step 4 — Update `executionkit/__init__.py`

Three edits:

1. Add import near the other pattern imports:
   ```python
   from executionkit.patterns.my_pattern import my_pattern
   ```

2. Add to `__all__` (keep alphabetical order):
   ```python
   "my_pattern",
   "my_pattern_sync",
   ```

3. Add sync wrapper at the bottom (before or after the existing wrappers):
   ```python
   def my_pattern_sync(
       provider: LLMProvider, prompt: str, **kwargs: Any
   ) -> PatternResult[str]:
       """Synchronous wrapper for :func:`my_pattern`."""
       return _run_sync(my_pattern(provider, prompt, **kwargs))
   ```
   If the pattern takes a non-`**kwargs` positional arg (like `react_loop`'s `tools`), spell it out explicitly.

## Step 5 — Write tests

Add a `TestMyPattern` class to `tests/test_patterns.py` (or a new `tests/test_my_pattern.py`).
Use `MockProvider` — no real API calls.

```python
from executionkit._mock import MockProvider
from executionkit.patterns.my_pattern import my_pattern

class TestMyPattern:
    async def test_basic(self) -> None:
        provider = MockProvider(responses=["expected output"])
        result = await my_pattern(provider, "test prompt")
        assert result.value == "expected output"
        assert result.cost.llm_calls == 1

    async def test_budget_exhausted(self) -> None:
        from executionkit.types import TokenUsage
        from executionkit.errors import BudgetExhaustedError
        provider = MockProvider(responses=["x"])
        with pytest.raises(BudgetExhaustedError):
            await my_pattern(provider, "p", max_cost=TokenUsage(llm_calls=0))
```

Cover: happy path, budget exhaustion, any pattern-specific error cases, and metadata keys.

## Step 6 — Add an example

Create `examples/my_pattern_example.py` following the structure of `examples/consensus_voting.py`:
- Module docstring with a `Run:` block showing the env var and command.
- `async def main()` that uses `Provider` as an async context manager.
- `asyncio.run(main())` guard.

## Step 7 — Add docs and update mkdocs.yml

Create `docs/patterns/my-pattern.md` with frontmatter:

```markdown
---
tags:
  - pattern
---

# My Pattern

Brief description and when to use vs. when not to use.

## Call flow  (mermaid sequenceDiagram)

## Minimal example

## Configuration knobs  (parameter table)

## Metadata keys  (key / type / meaning table)

## Cost characteristics

## Errors  (exception table)

## Source
```

Then add one line to `mkdocs.yml` under `nav:` in the Patterns block:

```yaml
      - My Pattern: patterns/my-pattern.md
```

## Step 8 — Run the validation gate

```
/validate
```

All four steps (ruff check, ruff format --check, mypy, pytest) must pass before pushing.
