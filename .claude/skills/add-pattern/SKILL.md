---
name: add-pattern
description: Add a public LLM call pattern to ExecutionKit, including tests and documentation.
---

# Add a pattern

Use this procedure only for a reusable call algorithm. Application-specific
branching belongs outside the package.

## 1. Define the contract

Write down:

- whether the function needs `LLMProvider` or `ToolCallingProvider`;
- its input, output `PatternResult` type, and defaults;
- its maximum calls and concurrency;
- how retry attempts and `max_cost` apply;
- all metadata keys and termination reasons;
- its trace events and checkpoint boundary; and
- failures that callers must handle.

## 2. Implement the async function

Create `executionkit/patterns/my_pattern.py`. Use `checked_complete()` or
`checked_stream()` so retry, budget, usage, and tracing behavior stays
consistent.

```python
"""Implementation of the my-pattern call flow."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from executionkit.cost import CostTracker
from executionkit.engine.messages import user_message
from executionkit.patterns.base import checked_complete
from executionkit.types import PatternResult, TokenUsage

if TYPE_CHECKING:
    from executionkit.engine.retry import RetryConfig
    from executionkit.observability import TraceCallback
    from executionkit.provider import LLMProvider


async def my_pattern(
    provider: LLMProvider,
    prompt: str,
    *,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
    trace: TraceCallback | None = None,
) -> PatternResult[str]:
    """Return one checked completion."""
    tracker = CostTracker()
    messages: list[dict[str, Any]] = [user_message(prompt)]
    response = await checked_complete(
        provider,
        messages,
        tracker,
        max_cost,
        retry,
        trace,
        max_tokens=max_tokens,
    )
    return PatternResult(
        value=response.content,
        cost=tracker.to_usage(),
        metadata=MappingProxyType({}),
    )
```

Validate arguments before the first provider call. Document every public
parameter, metadata key, and raised library error in the function docstring.

## 3. Export the function

Update:

- `executionkit/patterns/__init__.py`;
- `executionkit/__init__.py` and its alphabetical `__all__`; and
- the sync wrappers in `executionkit/__init__.py`.

The sync wrapper must use `_run_sync()` and must not duplicate pattern logic.

## 4. Test behavior

Use `MockProvider`; normal tests must not call a network endpoint. Cover:

- the successful result and exact usage;
- invalid arguments before dispatch;
- retry and partial-cost behavior;
- call and token budgets;
- concurrency bounds, if applicable;
- metadata and termination reasons; and
- cancellation or tool failures where relevant.

Add a named failure case to `tests/eval_failure_cases.py` only when the pattern
introduces a distinct model-output failure mode.

## 5. Update every public surface

Create `docs/patterns/my-pattern.md` with:

- when to use it and when not to;
- one runnable example;
- parameters and defaults;
- call count, concurrency, and budget behavior;
- metadata and errors; and
- the API reference directive.

Also update:

- the README pattern table;
- `docs/index.md`;
- `docs/patterns/index.md`;
- `docs/api/index.md` and `docs/api/core.md`;
- the MkDocs navigation;
- `scripts/check_doc_facts.py` `PATTERN_SLUGS`;
- `docs/architecture.md`; and
- `CHANGELOG.md`.

Add or update an ADR if the pattern changes an architecture boundary.

## 6. Validate

Run the repository validation skill. At minimum, the doc-fact check, strict
documentation build, lint, formatting, strict type checking, and full test
suite must pass.
