# ExecutionKit Merge Plan: Best-of-Both

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan ticket-by-ticket.

**Goal:** Merge patternmesh's behavioral correctness into executionkit while keeping executionkit's documentation, robustness, and design quality.

**Architecture:** Target the `executionkit/` flat layout as the working copy. Apply 9 targeted source changes in dependency order (foundation errors → base layer → patterns → composition → exports), then add missing tests and metadata improvements. All changes must pass `ruff check`, `ruff format --check`, `mypy --strict executionkit`, and `pytest --cov-fail-under=80`.

**Tech Stack:** Python 3.11+, pytest-asyncio, ruff, mypy --strict, hatchling

**Canonical source of behavioral truth:** `C:/Users/tandf/source/patternmesh/src/executionkit/`
**Merge target:** `C:/Users/tandf/source/executionkit/executionkit/`

---

## What Is Being Merged (and Why)

| Change | From | Rationale |
|--------|------|-----------|
| `ToolCallingProvider` protocol + `supports_tools` field on `Provider` | patternmesh | Plan spec: `react_loop` must validate capability at entry; `pipe` needs typed steps |
| `cost`/`metadata` kwargs on `ExecutionKitError.__init__` | patternmesh | `BudgetExhaustedError`, `MaxIterationsError`, `ConsensusFailedError` all need to carry cost for composition failure tracking |
| `was_truncated` checks `"max_tokens"` in addition to `"length"` | patternmesh | Anthropic-compatible; spec says check both |
| Robust `_parse_response` helpers (`_first_choice`, `_extract_content`, `_parse_tool_calls`, `_load_json`) | patternmesh | Defensive null-safe parsing; executionkit's direct index access can throw `KeyError` |
| `_note_truncation()` + `warnings.warn` in patterns | patternmesh | Spec: truncation must emit warning AND increment metadata counter |
| `_TrackedProvider` wrapper class | patternmesh | Used by `refine_loop` to auto-route all calls through budget+retry+truncation in one place |
| Per-field budget checks (input/output/calls separately) | patternmesh | Spec says fields are checked independently; executionkit combines input+output |
| `ToolCallingProvider` upfront check in `react_loop` | patternmesh | Spec: reject non-tool-capable providers at entry, not on first call |
| `truncated_observations` metadata + `_note_truncation` in `react_loop` | patternmesh | Spec: truncation metadata required |
| `MaxIterationsError` raised (not silent return) when `react_loop` exhausts rounds | patternmesh | Spec: iterative patterns raise on max-iterations |
| `PatternStep` Protocol + `_filter_kwargs` in `compose.py` | patternmesh | Spec: `pipe` must be type-safe; kwarg filtering prevents TypeError on incompatible steps |
| Per-step metadata list + error cost augmentation in `pipe` | patternmesh | Spec: partial cost must be preserved through child pattern failures |
| `PatternStep`, `MockProvider`, `ToolCallingProvider`, `checked_complete`, `validate_score` in `__init__.__all__` | patternmesh | Spec: these are public API; test_exports.py enforces it |
| `pyproject.toml`: classifiers, keywords, authors, pinned dev deps | patternmesh | Release readiness; PyPI discoverability |
| `tests/test_exports.py` (new file) | patternmesh | Smoke test for public API surface and sync-wrapper active-loop failure |

## What Stays From executionkit (Do NOT Overwrite)

- All docstrings and module-level documentation
- `engine/json_extraction.py` (3-tier extraction is superior)
- `engine/convergence.py` with `_scores` history list and `reset()` method
- `_mock.py` design (list cycling + `call_count`/`last_call` properties)
- `cost.py` (session CostTracker with `total_tokens` property)
- `patterns/consensus.py` `score=agreement_ratio` in PatternResult
- `patterns/refine_loop.py` initial response evaluation approach
- `_run_sync` / sync wrapper structure in `__init__.py`
- `_truncate` in `react_loop.py` (`\n[truncated]` marker is clearer than `...`)
- `provider.py` better HTTP error messages and `import urllib.error` style

---

## Agent Prompt Library

### AG-06 Python Backend Library Engineer
You are a senior Python package engineer implementing a typed, minimal-dependency public library. Implement exactly to the instructions in each ticket. Keep all existing docstrings, comments, and formatting intact. Only change what the ticket says to change. Run `ruff check executionkit/`, `ruff format --check executionkit/`, and `mypy --strict executionkit/` after each ticket. Never remove existing passing tests.

### AG-07 Testing and Quality Engineer
You are a staff test engineer. Add new assertions to existing test files without deleting existing tests. Every assertion must be a direct behavioral claim—no tests that merely check that code runs without error. After each ticket run `pytest tests/ -x -q` and confirm it passes.

### AG-08 Open Source Packaging Expert
You are an OSS maintainer. Make only the specific `pyproject.toml` changes listed. Do not change runtime dependencies, package layout, or tool configuration beyond what is listed.

---

## Execution Order

Sequential gates (must be done in order):
1. MB-001 → MB-002 (provider changes enable base.py budget/error semantics)
2. MB-002 → MB-003 (`_note_truncation` and `_TrackedProvider` from base.py are used in react_loop)
3. MB-001 → MB-004 (`ToolCallingProvider` import needed in compose)
4. MB-003 + MB-004 → MB-005 (exports depend on all source changes)

Parallel (safe to run after their dependencies):
- MB-006 (pyproject.toml) — no code dependencies, runs any time
- MB-007 (test_provider additions) — runs after MB-001
- MB-008 (test_exports new file) — runs after MB-005
- MB-009 (test_patterns additions) — runs after MB-003

MB-010 (quality gate) — runs last, after all other tickets.

---

## Task Board

### MB-001
**Owner:** `Python Backend Library Engineer`
**Agent prompt:** `AG-06 Python Backend Library Engineer`
**Mode:** `Sequential`
**Task:** Add `ToolCallingProvider` protocol, add `cost`/`metadata` to `ExecutionKitError`, fix `was_truncated`, and add robust parsing helpers to `provider.py`.

**Read first:**
- `executionkit/executionkit/provider.py` (the file to modify)
- `C:/Users/tandf/source/patternmesh/src/executionkit/provider.py` (reference for changes)

**Instructions:**

Make these 6 targeted changes to `executionkit/executionkit/provider.py`. Keep all existing docstrings.

**Change 1 — Add `Literal` to the imports line.**

Current imports include `from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable`.
Change to: `from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable`

**Change 2 — Add `TokenUsage` import.**

After the `from executionkit.types import` block (or add a new one):
```python
from executionkit.types import TokenUsage
```

**Change 3 — Add `cost`/`metadata` to `ExecutionKitError`.**

Replace the current:
```python
class ExecutionKitError(Exception):
    """Base exception for all ExecutionKit errors."""
```

With:
```python
class ExecutionKitError(Exception):
    """Base exception for all ExecutionKit errors."""

    def __init__(
        self,
        message: str,
        *,
        cost: TokenUsage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.cost: TokenUsage = cost if cost is not None else TokenUsage()
        self.metadata: dict[str, Any] = metadata if metadata is not None else {}
```

**Change 4 — Update `RateLimitError` to pass through `cost`/`metadata`.**

Replace the current `RateLimitError.__init__`:
```python
class RateLimitError(LLMError):
    """Provider returned HTTP 429 — retryable after ``retry_after`` seconds."""

    def __init__(self, message: str, *, retry_after: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after: float = retry_after
```

With:
```python
class RateLimitError(LLMError):
    """Provider returned HTTP 429 — retryable after ``retry_after`` seconds."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float = 1.0,
        cost: TokenUsage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, cost=cost, metadata=metadata)
        self.retry_after: float = retry_after
```

**Change 5 — Add `ToolCallingProvider` protocol after `LLMProvider`.**

After the closing `...` of the `LLMProvider` class body, add:
```python

@runtime_checkable
class ToolCallingProvider(LLMProvider, Protocol):
    """Extension of ``LLMProvider`` for providers that support tool calling.

    The built-in :class:`Provider` satisfies this protocol via its
    ``supports_tools`` attribute.  Pass to :func:`react_loop` to unlock
    tool-calling patterns.
    """

    supports_tools: Literal[True]
```

**Change 6 — Add `supports_tools` field to `Provider` dataclass.**

In the `Provider` dataclass, add this field after `timeout`:
```python
    supports_tools: Literal[True] = field(default=True, init=False)
```

Add `field` to the `from dataclasses import dataclass, field` import.

**Change 7 — Fix `was_truncated` to check both `"length"` and `"max_tokens"`.**

Replace:
```python
    @property
    def was_truncated(self) -> bool:
        return self.finish_reason == "length"
```

With:
```python
    @property
    def was_truncated(self) -> bool:
        return self.finish_reason in {"length", "max_tokens"}
```

**Change 8 — Fix URL path joining in `_post`.**

Replace:
```python
        url = f"{self.base_url.rstrip('/')}/{endpoint}"
```

With:
```python
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
```

**Change 9 — Replace `_parse_response` with null-safe version.**

Replace the current `_parse_response` method body with:
```python
    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        """Extract content, tool calls, and usage from the raw API response."""
        choice = _first_choice(data)
        message = choice.get("message", {})
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return LLMResponse(
            content=_extract_content(message.get("content")),
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
            finish_reason=str(choice.get("finish_reason", "stop")),
            usage=usage,
            raw=data,
        )
```

**Change 10 — Add module-level helper functions.**

After the `Provider` class definition and before any existing helpers, add these functions (copy from patternmesh; they replace the inline logic previously inside `_parse_response`):

```python
def _first_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("Provider response did not include any choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ProviderError("Provider choice payload was not an object")
    return choice


def _extract_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "output_text"}:
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict):
                    value = text.get("value")
                    if isinstance(value, str):
                        parts.append(value)
            elif isinstance(item.get("value"), str):
                parts.append(str(item["value"]))
        return "".join(parts)
    return str(content)


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    if raw_tool_calls is None:
        return []
    if not isinstance(raw_tool_calls, list):
        raise ProviderError("tool_calls payload was not a list")
    parsed: list[ToolCall] = []
    for raw_tc in raw_tool_calls:
        if not isinstance(raw_tc, dict):
            raise ProviderError("tool_call payload was not an object")
        function = raw_tc.get("function")
        if not isinstance(function, dict):
            raise ProviderError("tool_call.function payload was not an object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise ProviderError("tool_call.function.name was missing")
        arguments = _parse_tool_arguments(function.get("arguments"))
        tool_id = raw_tc.get("id")
        parsed.append(ToolCall(
            id=tool_id if isinstance(tool_id, str) else "",
            name=name,
            arguments=arguments,
        ))
    return parsed


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str):
        raise ProviderError("tool_call arguments must be a dict or JSON string")
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"tool_call arguments were not valid JSON: {arguments}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderError("tool_call arguments must decode to a JSON object")
    return parsed


def _load_json(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("Provider returned non-JSON data") from exc
    if not isinstance(loaded, dict):
        raise ProviderError("Provider returned a non-object JSON payload")
    return loaded
```

Also update `_post` to use `_load_json` when reading error bodies:
```python
            except urllib.error.HTTPError as exc:
                try:
                    raw = _load_json(exc.read())
                except ProviderError:
                    raw = {}
                status = exc.code
                if status == 429:
                    retry_after = float(
                        exc.headers.get("retry-after", "1") if exc.headers else 1
                    )
                    raise RateLimitError(
                        f"Rate limited (HTTP 429)",
                        retry_after=retry_after,
                    ) from exc
                if status in {401, 403, 404}:
                    raise PermanentError(
                        _format_http_error(status, raw)
                    ) from exc
                raise ProviderError(_format_http_error(status, raw)) from exc
```

Add `_format_http_error` from patternmesh (if not already present):
```python
def _format_http_error(status_code: int, payload: dict[str, Any]) -> str:
    message = payload.get("error")
    if isinstance(message, dict):
        detail = message.get("message")
        if isinstance(detail, str):
            return f"Provider request failed with HTTP {status_code}: {detail}"
    if isinstance(message, str):
        return f"Provider request failed with HTTP {status_code}: {message}"
    return f"Provider request failed with HTTP {status_code}"
```

**Verify after completing MB-001:**
```bash
cd C:/Users/tandf/source/executionkit
python -c "from executionkit.provider import ToolCallingProvider, Provider; p = Provider('http://x', 'y'); from typing import Literal; assert p.supports_tools is True"
python -c "from executionkit.provider import ExecutionKitError; from executionkit.types import TokenUsage; e = ExecutionKitError('x', cost=TokenUsage(1,2,3)); assert e.cost.llm_calls == 3"
python -c "from executionkit.provider import LLMResponse; r = LLMResponse(content='x', finish_reason='max_tokens'); assert r.was_truncated is True"
mypy --strict executionkit/
```

**Depends on:** none

**Out of scope:**
- Any change to `types.py`, `cost.py`, or `_mock.py`
- Changing the sync wrapper logic in `__init__.py`

**Handoff package:**
- `ToolCallingProvider` available for import from `executionkit.provider`
- `ExecutionKitError` accepts `cost` and `metadata` kwargs; all subclasses inherit this
- `was_truncated` returns `True` for both `"length"` and `"max_tokens"`
- `_parse_response` is null-safe via `_first_choice`, `_extract_content`, `_parse_tool_calls`

**Acceptance criteria:**
- `isinstance(Provider(...), ToolCallingProvider)` returns `True`
- `LLMResponse(finish_reason="max_tokens").was_truncated` is `True`
- `ExecutionKitError("x", cost=TokenUsage()).cost` is a `TokenUsage` instance
- `mypy --strict executionkit/` passes

---

### MB-002
**Owner:** `Python Backend Library Engineer`
**Agent prompt:** `AG-06 Python Backend Library Engineer`
**Mode:** `Sequential`
**Task:** Add `_note_truncation`, `_TrackedProvider`, and per-field budget checks to `patterns/base.py`.

**Read first:**
- `executionkit/executionkit/patterns/base.py` (the file to modify)
- `C:/Users/tandf/source/patternmesh/src/executionkit/patterns/base.py` (reference)

**Instructions:**

**Change 1 — Add `warnings` import.**

Add to the top-level imports:
```python
import warnings
```

Also add `Sequence` to the imports (needed by `_TrackedProvider.complete`):
```python
from collections.abc import Sequence
```

**Change 2 — Replace unified budget check with per-field budget checks in `checked_complete`.**

Replace the current `if budget is not None:` block inside `checked_complete`:
```python
    if budget is not None:
        total_budget = budget.input_tokens + budget.output_tokens
        if tracker.total_tokens >= total_budget > 0:
            raise BudgetExhaustedError(
                f"Token budget exhausted: {tracker.total_tokens} >= {total_budget}"
            )
        if budget.llm_calls > 0 and tracker._calls >= budget.llm_calls:
            raise BudgetExhaustedError(
                f"Call budget exhausted: {tracker._calls} >= {budget.llm_calls}"
            )
```

With:
```python
    if budget is not None:
        current = tracker.to_usage()
        if budget.llm_calls > 0 and current.llm_calls >= budget.llm_calls:
            raise BudgetExhaustedError(
                "LLM call budget exhausted before dispatch",
                cost=current,
                metadata={"budget": budget},
            )
        if budget.input_tokens > 0 and current.input_tokens >= budget.input_tokens:
            raise BudgetExhaustedError(
                "Input token budget exhausted before dispatch",
                cost=current,
                metadata={"budget": budget},
            )
        if budget.output_tokens > 0 and current.output_tokens >= budget.output_tokens:
            raise BudgetExhaustedError(
                "Output token budget exhausted before dispatch",
                cost=current,
                metadata={"budget": budget},
            )
```

**Change 3 — Add `_note_truncation` function after `checked_complete`.**

```python
def _note_truncation(
    response: LLMResponse, metadata: dict[str, Any], context: str
) -> None:
    """Increment truncated_responses counter and emit a warning if truncated.

    Args:
        response: The LLM response to inspect.
        metadata: The pattern's running metadata dict (mutated in place).
        context: Pattern name for the warning message (e.g. ``"react_loop"``).
    """
    if not response.was_truncated:
        return
    metadata["truncated_responses"] = int(metadata.get("truncated_responses", 0)) + 1
    warnings.warn(
        f"{context} returned a truncated response "
        f"(finish_reason={response.finish_reason!r})",
        stacklevel=3,
    )
```

**Change 4 — Add `_TrackedProvider` class after `_note_truncation`.**

```python
class _TrackedProvider:
    """Wraps an ``LLMProvider`` to auto-apply budget, retry, and truncation tracking.

    Used by patterns (e.g. ``refine_loop``) that need to call the provider
    multiple times while sharing a single ``CostTracker`` and metadata dict.
    """

    supports_tools: Literal[True] = True  # satisfies ToolCallingProvider protocol

    def __init__(
        self,
        provider: LLMProvider,
        tracker: CostTracker,
        metadata: dict[str, Any],
        *,
        budget: TokenUsage | None,
        retry: RetryConfig | None,
        context: str,
    ) -> None:
        self._provider = provider
        self._tracker = tracker
        self._metadata = metadata
        self._budget = budget
        self._retry = retry
        self._context = context

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Delegate to ``checked_complete`` and call ``_note_truncation``."""
        response = await checked_complete(
            self._provider,
            messages,
            self._tracker,
            self._budget,
            self._retry,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            **kwargs,
        )
        _note_truncation(response, self._metadata, self._context)
        return response
```

Add `Literal` to the imports at the top of the file:
```python
from typing import TYPE_CHECKING, Any, Literal
```

**Verify after completing MB-002:**
```bash
cd C:/Users/tandf/source/executionkit
python -c "from executionkit.patterns.base import _note_truncation, _TrackedProvider, checked_complete; print('OK')"
mypy --strict executionkit/
```

**Depends on:** MB-001 (for `cost`/`metadata` kwargs on `BudgetExhaustedError`)

**Out of scope:**
- Any change to `validate_score`
- Any change to `engine/` modules
- Modifying `refine_loop.py` to use `_TrackedProvider` (it already does)

**Handoff package:**
- `_note_truncation(response, metadata, context)` available from `patterns.base`
- `_TrackedProvider` class available from `patterns.base`
- Budget checks are now per-field (input/output/calls independently) with cost in error

**Acceptance criteria:**
- Calling `checked_complete` with a fully-exhausted `llm_calls` budget raises `BudgetExhaustedError` with a `cost` attribute
- `_note_truncation` emits `warnings.warn` when `response.was_truncated` is True
- `_TrackedProvider` satisfies `LLMProvider` protocol

---

### MB-003
**Owner:** `Python Backend Library Engineer`
**Agent prompt:** `AG-06 Python Backend Library Engineer`
**Mode:** `Sequential`
**Task:** Update `patterns/react_loop.py` to validate `ToolCallingProvider` at entry, track truncation, and raise `MaxIterationsError` on exhaustion.

**Read first:**
- `executionkit/executionkit/patterns/react_loop.py` (the file to modify)
- `C:/Users/tandf/source/patternmesh/src/executionkit/patterns/react_loop.py` (reference)

**Instructions:**

**Change 1 — Update imports.**

Replace:
```python
from executionkit.provider import LLMProvider  # noqa: TC001
```

With:
```python
from executionkit.provider import LLMProvider, MaxIterationsError, ToolCallingProvider  # noqa: TC001
```

Also add `_note_truncation` to the base import:
```python
from executionkit.patterns.base import checked_complete, _note_truncation
```

**Change 2 — Change the function signature.**

Replace `provider: LLMProvider` with `provider: ToolCallingProvider`:
```python
async def react_loop(
    provider: ToolCallingProvider,
    prompt: str,
    tools: Sequence[Tool],
    *,
    max_rounds: int = 8,
    max_observation_chars: int = 12000,
    tool_timeout: float | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
    **_: Any,
) -> PatternResult[str]:
```

Note: add `**_: Any` to accept (and ignore) extra kwargs from `pipe` composition.

**Change 3 — Add upfront provider validation as the first statement in the function body.**

After the docstring, before `tracker = CostTracker()`:
```python
    if not isinstance(provider, ToolCallingProvider) or not getattr(
        provider, "supports_tools", False
    ):
        raise TypeError(
            "react_loop() requires a ToolCallingProvider. "
            "Ensure the provider has supports_tools = True."
        )
```

**Change 4 — Add truncation metadata fields to the initial `metadata` dict.**

Replace:
```python
    tracker = CostTracker()
    tool_schemas = [tool.to_schema() for tool in tools]
    tool_lookup: dict[str, Tool] = {tool.name: tool for tool in tools}

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    total_tool_calls = 0
    final_content = ""
```

With:
```python
    tracker = CostTracker()
    metadata: dict[str, Any] = {
        "rounds": 0,
        "tool_calls_made": 0,
        "truncated_responses": 0,
        "truncated_observations": 0,
    }
    tool_schemas = [tool.to_schema() for tool in tools]
    tool_lookup: dict[str, Tool] = {tool.name: tool for tool in tools}
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
```

**Change 5 — Call `_note_truncation` after each LLM response and update `metadata["rounds"]`.**

After the `response = await checked_complete(...)` call, add:
```python
        _note_truncation(response, metadata, "react_loop")
        metadata["rounds"] = round_num
```

**Change 6 — Track `tool_calls_made` per observation and `truncated_observations`.**

In the tool execution loop, update the metadata tracking. Replace the block that currently increments `total_tool_calls`:
```python
        for tc in response.tool_calls:
            total_tool_calls += 1
            observation = await _execute_tool_call(...)
```

With:
```python
        for tc in response.tool_calls:
            metadata["tool_calls_made"] = int(metadata["tool_calls_made"]) + 1
            raw_observation = await _execute_tool_call(...)
            observation = _truncate(raw_observation, max_observation_chars)
            if len(observation) < len(raw_observation):
                metadata["truncated_observations"] = (
                    int(metadata["truncated_observations"]) + 1
                )
```

Update the `messages.append` for the tool role to use `observation` (the already-truncated version); remove `_truncate` from the inline message append.

**Change 7 — Update early return to use `metadata` dict.**

Replace the early return (when no tool calls) with:
```python
        if not response.has_tool_calls:
            return PatternResult[str](
                value=response.content,
                score=None,
                cost=tracker.to_usage(),
                metadata=dict(metadata),
            )
```

**Change 8 — Replace the silent return-on-exhaustion with `MaxIterationsError`.**

Remove the current `# max_rounds exhausted` block at the end of the function and replace with:
```python
    raise MaxIterationsError(
        "react_loop() reached max_rounds without a final answer",
        cost=tracker.to_usage(),
        metadata=dict(metadata),
    )
```

**Verify after completing MB-003:**
```bash
cd C:/Users/tandf/source/executionkit
python -c "
import asyncio
from executionkit.provider import LLMProvider, LLMResponse
from executionkit.patterns.react_loop import react_loop

class BadProvider:
    async def complete(self, messages, **kwargs): return LLMResponse(content='x')

async def test():
    try:
        await react_loop(BadProvider(), 'prompt', [])
        assert False, 'should have raised'
    except TypeError as e:
        assert 'ToolCallingProvider' in str(e)

asyncio.run(test())
print('Provider validation OK')
"
mypy --strict executionkit/
```

**Depends on:** MB-001 (for `ToolCallingProvider`, `MaxIterationsError` with cost kwarg), MB-002 (for `_note_truncation`)

**Out of scope:**
- Changing `_execute_tool_call` internals
- Changing `_truncate` function (keep `\n[truncated]` marker)

**Handoff package:**
- `react_loop` rejects non-tool-capable providers with `TypeError` at entry
- `react_loop` raises `MaxIterationsError` (with cost/metadata) when rounds exhausted
- `react_loop` emits truncation warnings and counts via `_note_truncation`
- `react_loop` accepts `**_: Any` for safe use in `pipe` chains

**Acceptance criteria:**
- `react_loop(LLMProvider(), ...)` raises `TypeError` immediately
- `react_loop` raises `MaxIterationsError` (not returns) when `max_rounds` is exhausted
- Metadata dict always contains `truncated_responses` and `truncated_observations` keys

---

### MB-004
**Owner:** `Python Backend Library Engineer`
**Agent prompt:** `AG-06 Python Backend Library Engineer`
**Mode:** `Sequential`
**Task:** Add `PatternStep` Protocol, `_filter_kwargs`, per-step metadata, and error cost augmentation to `compose.py`.

**Read first:**
- `executionkit/executionkit/compose.py` (the file to modify)
- `C:/Users/tandf/source/patternmesh/src/executionkit/compose.py` (reference)

**Instructions:**

**Change 1 — Update imports.**

Replace:
```python
from typing import Any

from executionkit.provider import LLMProvider  # noqa: TC001
from executionkit.types import PatternResult, TokenUsage
```

With:
```python
import inspect
from collections.abc import Awaitable
from typing import Any, Protocol

from executionkit.provider import ExecutionKitError, LLMProvider  # noqa: TC001
from executionkit.types import PatternResult, TokenUsage
```

**Change 2 — Add `PatternStep` Protocol before the `_subtract` helper.**

```python
class PatternStep(Protocol):
    """Callable protocol for a single step in a :func:`pipe` chain.

    Each step must accept ``(provider, prompt, **kwargs)`` and return an
    awaitable :class:`~executionkit.types.PatternResult`.  Extra keyword
    arguments (e.g. ``max_cost``) are filtered to only those the step
    actually accepts, so steps that do not declare ``**kwargs`` will not
    receive unsupported arguments.
    """

    def __call__(
        self,
        provider: LLMProvider,
        prompt: str,
        **kwargs: Any,
    ) -> Awaitable[PatternResult[Any]]: ...
```

**Change 3 — Update `pipe` signature to use `PatternStep` type.**

Replace `*steps: Any` with `*steps: PatternStep`.

**Change 4 — Rewrite the `pipe` loop body to add kwarg filtering, per-step metadata, and error cost augmentation.**

Replace the current loop body:
```python
    cumulative_cost = TokenUsage()
    current_prompt: str = prompt

    final_result: PatternResult[Any] = PatternResult(value=prompt)

    for step in steps:
        if max_budget is not None:
            remaining = _subtract(max_budget, cumulative_cost)
            result: PatternResult[Any] = await step(
                provider,
                current_prompt,
                max_cost=remaining,
                **shared_kwargs,
            )
        else:
            result = await step(provider, current_prompt, **shared_kwargs)

        cumulative_cost = cumulative_cost + result.cost
        current_prompt = str(result.value)
        final_result = result

    # Return the last result but with the merged cumulative cost
    return PatternResult(
        value=final_result.value,
        score=final_result.score,
        cost=cumulative_cost,
        metadata=final_result.metadata,
    )
```

With:
```python
    total_cost = TokenUsage()
    current_prompt: str = prompt
    last_result: PatternResult[Any] | None = None
    step_metadata: list[dict[str, Any]] = []

    for step in steps:
        step_kwargs = dict(shared_kwargs)
        if max_budget is not None:
            step_kwargs["max_cost"] = _subtract(max_budget, total_cost)
        filtered_kwargs = _filter_kwargs(step, step_kwargs)

        try:
            result: PatternResult[Any] = await step(
                provider, current_prompt, **filtered_kwargs
            )
        except ExecutionKitError as exc:
            exc.cost = total_cost + exc.cost
            raise

        total_cost = total_cost + result.cost
        current_prompt = str(result.value)
        step_metadata.append(dict(result.metadata))
        last_result = result

    assert last_result is not None  # guarded by `if not steps` early return
    final_metadata = dict(last_result.metadata)
    final_metadata["step_count"] = len(steps)
    final_metadata["step_metadata"] = step_metadata
    return PatternResult(
        value=last_result.value,
        score=last_result.score,
        cost=total_cost,
        metadata=final_metadata,
    )
```

**Change 5 — Add `_filter_kwargs` helper after `_subtract`.**

```python
def _filter_kwargs(step: PatternStep, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Filter ``kwargs`` to only keys accepted by ``step``'s signature.

    If the step declares ``**kwargs``, all keys are passed through.
    Otherwise only parameters explicitly listed in the signature are kept.
    This prevents ``TypeError`` when chaining patterns with different
    keyword argument sets.
    """
    try:
        sig = inspect.signature(step)
    except (ValueError, TypeError):
        return kwargs  # uninspectable callable — pass everything

    params = sig.parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs  # step accepts **kwargs — pass everything

    allowed = {
        name
        for name, p in params.items()
        if name not in {"provider", "prompt"}
        and p.kind
        in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    return {k: v for k, v in kwargs.items() if k in allowed}
```

**Verify after completing MB-004:**
```bash
cd C:/Users/tandf/source/executionkit
python -c "from executionkit.compose import PatternStep, pipe, _filter_kwargs; print('OK')"
mypy --strict executionkit/
```

**Depends on:** MB-001 (for `ExecutionKitError` with mutable `.cost` attribute)

**Out of scope:**
- Any change to `kit.py`
- Any change to patterns themselves

**Handoff package:**
- `PatternStep` Protocol defined in `compose.py` and ready to export
- `pipe` accumulates per-step metadata in `result.metadata["step_metadata"]`
- `pipe` augments `ExecutionKitError.cost` with partial cost before re-raising
- `_filter_kwargs` prevents `TypeError` from mismatched step signatures

**Acceptance criteria:**
- `from executionkit.compose import PatternStep` works
- `pipe` with a step that raises `ExecutionKitError` re-raises with augmented cost
- `_filter_kwargs` drops keys not in step signature unless step has `**kwargs`

---

### MB-005
**Owner:** `Python Backend Library Engineer`
**Agent prompt:** `AG-06 Python Backend Library Engineer`
**Mode:** `Sequential`
**Task:** Add `PatternStep`, `MockProvider`, `ToolCallingProvider`, `checked_complete`, `validate_score` to `__init__.py` exports.

**Read first:**
- `executionkit/executionkit/__init__.py` (the file to modify)
- `C:/Users/tandf/source/patternmesh/src/executionkit/__init__.py` (reference for what to add)

**Instructions:**

**Change 1 — Add new imports.**

Add to the imports block:
```python
from executionkit._mock import MockProvider
from executionkit.compose import PatternStep
from executionkit.patterns.base import checked_complete, validate_score
from executionkit.provider import ToolCallingProvider
```

Keep all existing imports. These are additions only.

**Change 2 — Add new names to `__all__`.**

Add these entries to the `__all__` list (in alphabetical order with existing entries):
```python
    "MockProvider",
    "PatternStep",
    "ToolCallingProvider",
    "checked_complete",
    "validate_score",
```

**Change 3 — Fix `react_loop_sync` signature to use `ToolCallingProvider`.**

Replace:
```python
def react_loop_sync(
    provider: LLMProvider,
    prompt: str,
    tools: Sequence[Tool] = (),
    **kwargs: Any,
) -> PatternResult[str]:
```

With:
```python
def react_loop_sync(
    provider: ToolCallingProvider,
    prompt: str,
    tools: Sequence[Tool] = (),
    **kwargs: Any,
) -> PatternResult[str]:
```

**Verify after completing MB-005:**
```bash
cd C:/Users/tandf/source/executionkit
python -c "
import executionkit as ek
required = {'PatternStep', 'MockProvider', 'ToolCallingProvider', 'checked_complete', 'validate_score'}
missing = required - set(ek.__all__)
assert not missing, f'Missing from __all__: {missing}'
print('All exports present')
"
mypy --strict executionkit/
```

**Depends on:** MB-001, MB-003, MB-004

**Out of scope:**
- Removing any existing exports
- Changing sync wrapper behavior

**Handoff package:**
- `PatternStep`, `MockProvider`, `ToolCallingProvider`, `checked_complete`, `validate_score` all in `__all__`
- `react_loop_sync` now accepts `ToolCallingProvider`

**Acceptance criteria:**
- All 5 new names present in `ek.__all__`
- `from executionkit import PatternStep, MockProvider, ToolCallingProvider` works
- `mypy --strict` passes

---

### MB-006
**Owner:** `Open Source Packaging Expert`
**Agent prompt:** `AG-08 Open Source Packaging Expert`
**Mode:** `Parallel`
**Task:** Improve `pyproject.toml` metadata for PyPI release readiness.

**Read first:**
- `executionkit/pyproject.toml` (the file to modify)
- `C:/Users/tandf/source/patternmesh/pyproject.toml` (reference for metadata)

**Instructions:**

**Change 1 — Add `readme`, `authors`, `keywords`, and `classifiers` to `[project]`.**

After the `license = "MIT"` line, add:
```toml
readme = "README.md"
authors = [
  { name = "ExecutionKit contributors" },
]
keywords = [
  "llm",
  "openai-compatible",
  "reasoning",
  "tool-calling",
]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Topic :: Software Development :: Libraries :: Python Modules",
  "Typing :: Typed",
]
```

**Change 2 — Update dev dependency pins to match patternmesh's more recent versions.**

Replace:
```toml
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
    "mypy>=1.0",
]
```

With:
```toml
dev = [
    "build>=1.2",
    "mypy>=1.18",
    "pytest>=8.4",
    "pytest-asyncio>=1.2",
    "pytest-cov>=7.0",
    "ruff>=0.14.0",
]
```

**Change 3 — Add `addopts` for automatic coverage to `[tool.pytest.ini_options]`.**

Add:
```toml
addopts = "--cov=executionkit --cov-report=term-missing"
```

**Verify after completing MB-006:**
```bash
cd C:/Users/tandf/source/executionkit
pip install -e ".[dev]" --quiet
python -c "import executionkit; print('install OK')"
```

**Depends on:** none

**Out of scope:**
- Changing `packages` path (keep flat `executionkit/` layout)
- Adding GitHub Actions CI (out of scope for this merge)
- Changing lint rule selection

**Handoff package:**
- `pyproject.toml` has full PyPI metadata
- Dev deps pinned to stable recent versions

**Acceptance criteria:**
- `pip install -e ".[dev]"` installs without error
- All 5 classifier entries present in `pyproject.toml`

---

### MB-007
**Owner:** `Testing and Quality Engineer`
**Agent prompt:** `AG-07 Testing and Quality Engineer`
**Mode:** `Parallel` (after MB-001)
**Task:** Add `was_truncated` for `"max_tokens"` and `ToolCallingProvider` isinstance tests to `test_provider.py`.

**Read first:**
- `executionkit/tests/test_provider.py` (the file to modify)
- `C:/Users/tandf/source/patternmesh/tests/test_provider.py` (reference for what assertions to add)

**Instructions:**

Add the following test cases to the `TestLLMResponse` class in `tests/test_provider.py`:

```python
    def test_was_truncated_when_finish_reason_max_tokens(self) -> None:
        r = LLMResponse(content="truncated...", finish_reason="max_tokens")
        assert r.was_truncated is True

    def test_was_truncated_false_when_tool_calls(self) -> None:
        r = LLMResponse(content="", finish_reason="tool_calls")
        assert r.was_truncated is False
```

Add the following test to the `TestProvider` class:

```python
    def test_provider_satisfies_tool_calling_provider_protocol(self) -> None:
        from executionkit.provider import ToolCallingProvider
        p = Provider(base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        assert isinstance(p, ToolCallingProvider)

    def test_execution_kit_error_carries_cost_and_metadata(self) -> None:
        from executionkit.provider import ExecutionKitError
        from executionkit.types import TokenUsage
        err = ExecutionKitError("fail", cost=TokenUsage(1, 2, 3), metadata={"k": "v"})
        assert err.cost == TokenUsage(1, 2, 3)
        assert err.metadata == {"k": "v"}

    def test_execution_kit_error_defaults_to_zero_cost(self) -> None:
        from executionkit.provider import ExecutionKitError
        from executionkit.types import TokenUsage
        err = ExecutionKitError("fail")
        assert err.cost == TokenUsage()
        assert err.metadata == {}
```

**Run after adding tests:**
```bash
cd C:/Users/tandf/source/executionkit
pytest tests/test_provider.py -v
```

Expected: all new tests PASS.

**Depends on:** MB-001

**Out of scope:**
- Changing existing tests
- Adding HTTP mock tests (patternmesh's test_provider has these but they use the `from urllib import request` import style; executionkit uses `urllib.request` — don't add HTTP mock tests for this ticket)

**Acceptance criteria:**
- `test_was_truncated_when_finish_reason_max_tokens` passes
- `test_provider_satisfies_tool_calling_provider_protocol` passes
- No existing tests broken

---

### MB-008
**Owner:** `Testing and Quality Engineer`
**Agent prompt:** `AG-07 Testing and Quality Engineer`
**Mode:** `Parallel` (after MB-005)
**Task:** Create `tests/test_exports.py` — smoke test for public API surface and sync-wrapper active-loop failure.

**Read first:**
- `C:/Users/tandf/source/patternmesh/tests/test_exports.py` (reference)
- `executionkit/executionkit/__init__.py` (to know what `__all__` contains after MB-005)

**Instructions:**

Create `executionkit/tests/test_exports.py`:

```python
"""Smoke tests for the public API surface and sync wrapper behavior."""

from __future__ import annotations

import pytest

import executionkit as ek
from executionkit._mock import MockProvider
from executionkit.provider import LLMResponse


def _make_response(text: str) -> LLMResponse:
    return LLMResponse(content=text, finish_reason="stop")


class TestPublicExports:
    """All required names must appear in __all__."""

    def test_core_patterns_exported(self) -> None:
        required = {"consensus", "refine_loop", "react_loop", "pipe"}
        assert required.issubset(set(ek.__all__))

    def test_sync_wrappers_exported(self) -> None:
        required = {"consensus_sync", "refine_loop_sync", "react_loop_sync", "pipe_sync"}
        assert required.issubset(set(ek.__all__))

    def test_types_exported(self) -> None:
        required = {
            "PatternResult",
            "TokenUsage",
            "Tool",
            "VotingStrategy",
            "Evaluator",
            "PatternStep",
        }
        assert required.issubset(set(ek.__all__))

    def test_provider_types_exported(self) -> None:
        required = {
            "Provider",
            "LLMProvider",
            "ToolCallingProvider",
            "LLMResponse",
            "ToolCall",
        }
        assert required.issubset(set(ek.__all__))

    def test_error_classes_exported(self) -> None:
        required = {
            "ExecutionKitError",
            "LLMError",
            "RateLimitError",
            "PermanentError",
            "ProviderError",
            "PatternError",
            "BudgetExhaustedError",
            "ConsensusFailedError",
            "MaxIterationsError",
        }
        assert required.issubset(set(ek.__all__))

    def test_utilities_exported(self) -> None:
        required = {
            "Kit",
            "CostTracker",
            "RetryConfig",
            "ConvergenceDetector",
            "MockProvider",
            "checked_complete",
            "validate_score",
            "extract_json",
            "DEFAULT_RETRY",
        }
        assert required.issubset(set(ek.__all__))


class TestSyncWrapperActiveLoopFailure:
    """Sync wrappers must fail fast inside a running event loop."""

    @pytest.mark.asyncio
    async def test_consensus_sync_fails_in_active_loop(self) -> None:
        provider = MockProvider(responses=["alpha", "alpha"])
        with pytest.raises(RuntimeError):
            ek.consensus_sync(provider, "prompt", num_samples=2)

    @pytest.mark.asyncio
    async def test_pipe_sync_fails_in_active_loop(self) -> None:
        provider = MockProvider(responses=["result"])
        with pytest.raises(RuntimeError):
            ek.pipe_sync(provider, "prompt")


class TestConsensusSmoke:
    """Basic sync smoke test to verify the wrapper chain works end-to-end."""

    def test_consensus_sync_returns_majority_value(self) -> None:
        provider = MockProvider(
            responses=[_make_response("alpha"), _make_response("alpha")]
        )
        result = ek.consensus_sync(provider, "prompt", num_samples=2)
        assert result.value == "alpha"
```

**Run after creating the file:**
```bash
cd C:/Users/tandf/source/executionkit
pytest tests/test_exports.py -v
```

Expected: all tests PASS.

**Depends on:** MB-005

**Out of scope:**
- Testing every pattern in depth (that's covered by test_patterns.py)

**Acceptance criteria:**
- File is created at `tests/test_exports.py`
- All test classes in the file pass
- `TestSyncWrapperActiveLoopFailure` tests confirm `RuntimeError` is raised inside async context

---

### MB-009
**Owner:** `Testing and Quality Engineer`
**Agent prompt:** `AG-07 Testing and Quality Engineer`
**Mode:** `Parallel` (after MB-003)
**Task:** Add `react_loop` provider validation and truncation metadata tests to `tests/test_patterns.py`.

**Read first:**
- `executionkit/tests/test_patterns.py` (the file to modify)
- `C:/Users/tandf/source/patternmesh/tests/patterns/test_react_loop.py` (reference)

**Instructions:**

Add these test cases to the existing `react_loop` section of `tests/test_patterns.py`.

First, ensure the conftest or test file has a helper for a mock `ToolCallingProvider`. Add this at the top of the react_loop test section:

```python
from executionkit.provider import LLMProvider, LLMResponse, ToolCallingProvider
from executionkit.types import Tool


class _NonToolProvider:
    """A provider that does NOT satisfy ToolCallingProvider (no supports_tools)."""

    async def complete(self, messages: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="answer")
```

Add these test cases:

```python
class TestReactLoopProviderValidation:
    """react_loop must reject non-ToolCallingProvider at entry."""

    @pytest.mark.asyncio
    async def test_rejects_plain_llm_provider(self) -> None:
        provider = _NonToolProvider()
        with pytest.raises(TypeError, match="ToolCallingProvider"):
            await react_loop(provider, "prompt", [])  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_accepts_tool_calling_provider(self) -> None:
        from executionkit._mock import MockProvider
        provider = MockProvider(responses=["final answer"])
        result = await react_loop(provider, "prompt", [])
        assert result.value == "final answer"

    @pytest.mark.asyncio
    async def test_result_has_truncation_metadata_keys(self) -> None:
        from executionkit._mock import MockProvider
        provider = MockProvider(responses=["done"])
        result = await react_loop(provider, "prompt", [])
        assert "truncated_responses" in result.metadata
        assert "truncated_observations" in result.metadata

    @pytest.mark.asyncio
    async def test_max_rounds_exhaustion_raises_max_iterations_error(self) -> None:
        from executionkit._mock import MockProvider
        from executionkit.provider import MaxIterationsError, ToolCall

        # Always return tool calls so the loop never terminates naturally
        tool_call_response = LLMResponse(
            content="",
            finish_reason="tool_calls",
            tool_calls=[ToolCall(id="1", name="search", arguments={"q": "x"})],
        )
        provider = MockProvider(responses=[tool_call_response] * 10)

        async def _search(q: str) -> str:
            return "result"

        tool = Tool(
            name="search",
            description="search",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
            execute=_search,
        )

        with pytest.raises(MaxIterationsError) as exc_info:
            await react_loop(provider, "prompt", [tool], max_rounds=2)

        err = exc_info.value
        assert err.cost is not None
        assert err.metadata["rounds"] == 2
```

**Run after adding tests:**
```bash
cd C:/Users/tandf/source/executionkit
pytest tests/test_patterns.py -v -k "react"
```

Expected: all new tests PASS.

**Depends on:** MB-003

**Out of scope:**
- Truncation warning assertion (requires `pytest.warns` — add only if easy to wire in)
- Modifying existing passing tests

**Acceptance criteria:**
- `test_rejects_plain_llm_provider` confirms `TypeError` raised before any LLM call
- `test_max_rounds_exhaustion_raises_max_iterations_error` confirms `MaxIterationsError.cost` is set
- `test_result_has_truncation_metadata_keys` confirms metadata shape

---

### MB-010
**Owner:** `Testing and Quality Engineer`
**Agent prompt:** `AG-07 Testing and Quality Engineer`
**Mode:** `Sequential` (final gate — runs after MB-001 through MB-009)
**Task:** Run the full quality gate and confirm all checks pass.

**Read first:**
- All source files in `executionkit/executionkit/`
- `executionkit/pyproject.toml`

**Instructions:**

Run each check in order. If any fail, fix the issue before proceeding.

**Step 1 — Lint:**
```bash
cd C:/Users/tandf/source/executionkit
ruff check executionkit/ tests/
```
Expected: zero errors.

**Step 2 — Format check:**
```bash
ruff format --check executionkit/ tests/
```
Expected: zero reformatting needed.

**Step 3 — Type check:**
```bash
mypy --strict executionkit/
```
Expected: `Success: no issues found`.

**Step 4 — Tests with coverage:**
```bash
pytest tests/ -x -q --cov=executionkit --cov-report=term-missing --cov-fail-under=80
```
Expected: all tests pass, coverage ≥ 80%.

**Step 5 — Import smoke test:**
```bash
python -c "
import executionkit as ek
print('version:', getattr(ek, '__version__', 'n/a'))
# Verify all critical new exports are importable
from executionkit import (
    PatternStep, MockProvider, ToolCallingProvider,
    checked_complete, validate_score, extract_json,
)
# Verify ToolCallingProvider protocol check works
from executionkit.provider import Provider
assert isinstance(Provider('http://x', 'y'), ToolCallingProvider)
print('All smoke checks passed')
"
```

**Step 6 — Example imports:**
```bash
python -c "import examples.quickstart_openai" 2>&1 | head -5
python -c "import examples.quickstart_ollama" 2>&1 | head -5
```
Expected: no `ImportError` (runtime errors from missing API keys are acceptable).

**Deliverables:**
- Pass/fail report for each of the 6 checks above
- If any check fails, document the exact error and the fix applied

**Depends on:** MB-001 through MB-009

**Out of scope:**
- Adding new features to fix quality gate failures
- Relaxing type strictness or coverage threshold

**Acceptance criteria:**
- All 6 checks pass without modification to coverage thresholds or type strictness settings
- No new `mypy` errors introduced by the merge changes
- Full test suite passes: `pytest tests/ -x`

---

## Definition of Done

The merge is complete when:

- All 9 source change tickets (MB-001 through MB-005) are merged into `executionkit/executionkit/`
- MB-006 `pyproject.toml` improvements are applied
- All 3 test tickets (MB-007, MB-008, MB-009) pass
- MB-010 quality gate passes clean: ruff, mypy --strict, pytest --cov-fail-under=80
- `executionkit` is not changed in scope — no new patterns, no new provider abstractions, no framework features
- The following behaviors are now present:
  - `react_loop` rejects non-`ToolCallingProvider` at entry with `TypeError`
  - `was_truncated` returns `True` for both `"length"` and `"max_tokens"`
  - Truncation emits `warnings.warn` AND increments `metadata["truncated_responses"]`
  - `pipe` preserves partial cost through child pattern failures
  - `PatternStep`, `MockProvider`, `ToolCallingProvider` are in `ek.__all__`
  - `MaxIterationsError` is raised (not silently returned) when `react_loop` exhausts rounds
