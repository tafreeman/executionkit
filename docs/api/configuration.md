# Configuration reference

This page lists the public defaults that affect calls, retries, budgets, tools,
sessions, and live evaluation. Pattern-specific behavior is explained on each
[pattern page](../patterns/index.md).

## Provider

```text
Provider(
    base_url: str,
    model: str,
    api_key: str = "",
    default_temperature: float = 0.7,
    default_max_tokens: int = 4096,
    timeout: float = 120.0,
)
```

`base_url` must use `http` or `https`. The client appends
`/chat/completions`. Redirects are not followed.

The provider defaults apply when `Provider.complete()` or `Provider.stream()`
receives `None` for that argument. Public patterns pass their own temperature
and token defaults, so configure those on the pattern call.

## RetryConfig

```text
RetryConfig(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable: tuple[type[Exception], ...] = (
        RateLimitError,
        ProviderError,
    ),
    rate_limit_strategy: TokenBucket | None = None,
)
```

`max_retries` counts retries after the initial attempt. The default permits at
most four attempts. Backoff uses full jitter between zero and the capped
exponential delay.

!!! warning "Behavior change in 0.4.0 — verify your installed version"
    The paragraph above describes 0.4.0 and later. **0.3.0 and earlier**
    instead treat `max_retries` as the *total* attempt count, so
    `RetryConfig(max_retries=3)` makes at most 3 attempts, not 4. The change
    makes `RetryConfig` agree with `structured()`'s own `max_retries`, which
    has always run `1 + max_retries` attempts.

    **Migrating from 0.3.0:** to keep an existing call's attempt count exactly
    the same after upgrading, decrement `max_retries` by one
    (`max_retries=N` → `max_retries=N-1`). `max_retries=0` is unchanged either
    version — always a single attempt, no retries. A negative `max_retries`
    now raises `ValueError` instead of silently making zero attempts and
    surfacing `RuntimeError("unreachable")`. One budget-interaction edge case:
    if a pattern's `max_cost` sets an `llm_calls` ceiling equal to the *old*
    attempt count, a persistently failing call now ends in
    `BudgetExhaustedError` (a `PatternError`) instead of the provider's own
    `ProviderError` one attempt earlier — widen an `except ProviderError` that
    relied on that ceiling. See the `[0.4.0]` section of
    [CHANGELOG.md](https://github.com/tafreeman/executionkit/blob/main/CHANGELOG.md#040---2026-09-23)
    for the authoritative entry.

`rate_limit_strategy` acquires one token before every provider attempt. After a
`RateLimitError`, it applies the error's `retry_after` value before the next
attempt.

## TokenBucket

```text
TokenBucket(rate: float, capacity: float)
```

- `rate` is the number of tokens added per second and must be greater than zero.
- `capacity` is the maximum burst size and must be at least one.
- Each `acquire()` consumes one token.
- The object is intended for one asyncio event loop and is not thread-safe.

A bucket on `RetryConfig` controls individual provider attempts. A bucket on
`Kit(rate_limiter=...)` controls top-level Kit method calls. They are separate
limits.

## Call and token budgets

Patterns accept `max_cost=TokenUsage(...)`. `pipe()` calls its shared budget
`max_budget`.

```python
from executionkit import TokenUsage

budget = TokenUsage(
    input_tokens=20_000,
    output_tokens=5_000,
    llm_calls=12,
)
```

A zero field means unlimited. LLM call slots are reserved before dispatch, so
the call count includes retry attempts and is enforced across concurrent tasks
in one asyncio event loop. Token totals are checked before dispatch; a
successful response can cross a token limit because its usage is known only
after it returns. A later call is then blocked.

`CostTracker` and the budget implementation are not safe for concurrent use
from multiple threads.

## Pattern defaults

### consensus

| Parameter | Default | Meaning |
|---|---:|---|
| `num_samples` | `5` | Concurrent candidate calls. |
| `strategy` | `"majority"` | `"majority"` or `"unanimous"`. |
| `temperature` | `0.9` | Sampling temperature. |
| `max_tokens` | `4096` | Maximum output tokens per call. |
| `max_concurrency` | `5` | Maximum candidates in flight. |
| `retry` | `None` | Uses `DEFAULT_RETRY`. |
| `max_cost` | `None` | No pattern budget. |
| `trace` | `None` | No trace callback. |

### refine_loop

| Parameter | Default | Meaning |
|---|---:|---|
| `evaluator` | `None` | Uses the built-in model evaluator. |
| `max_eval_chars` | `32768` | Maximum candidate characters sent to the evaluator. |
| `target_score` | `0.9` | Stop at or above this score. |
| `max_iterations` | `5` | Maximum refinement rounds after the initial generation. |
| `patience` | `3` | Stop after this many small improvements. |
| `delta_threshold` | `0.01` | Improvement considered meaningful. |
| `temperature` | `0.7` | Generation temperature. |
| `max_tokens` | `4096` | Maximum output tokens per call. |
| `max_cost` | `None` | No pattern budget. |
| `retry` | `None` | Uses `DEFAULT_RETRY`. |
| `trace` | `None` | No trace callback. |
| `on_checkpoint` | `None` | No iteration callback. |

### react_loop

| Parameter | Default | Meaning |
|---|---:|---|
| `tools` | `()` | No tools. |
| `messages` | `None` | Start from `prompt`; mutually exclusive with `prompt`. |
| `max_rounds` | `8` | Maximum model and tool rounds. |
| `max_observation_chars` | `12000` | Per-tool-result text limit. |
| `tool_timeout` | `None` | Use each tool's own timeout. |
| `max_tool_calls_per_round` | `32` | Maximum calls accepted from one model response. |
| `temperature` | `0.3` | Model temperature. |
| `max_tokens` | `4096` | Maximum output tokens per call. |
| `max_cost` | `None` | No pattern budget. |
| `retry` | `None` | Uses `DEFAULT_RETRY`. |
| `max_history_messages` | `None` | Do not trim message history. |
| `trace` | `None` | No trace callback. |
| `approval_gate` | `None` | Execute valid tool calls without an approval callback. |
| `redact_trace_args` | `True` | Omit tool arguments from trace events. |
| `on_checkpoint` | `None` | No round callback. |
| `summarizer` | `None` | Drop old messages instead of summarizing them when trimming. |

Tool calls in the same round run concurrently. `tool_timeout` overrides every
tool's configured timeout when it is not `None`.

### structured

| Parameter | Default | Meaning |
|---|---:|---|
| `validator` | `None` | Parse JSON without an application validator. |
| `max_retries` | `3` | Maximum repair calls after the first response. |
| `temperature` | `0.0` | Model temperature. |
| `max_tokens` | `4096` | Maximum output tokens per call. |
| `max_cost` | `None` | No pattern budget. |
| `retry` | `None` | Uses `DEFAULT_RETRY` for each provider call. |
| `trace` | `None` | No trace callback. |
| `stream` | `False` | `True` is rejected because repair needs complete responses. |

`structured.max_retries` is a repair count. It is separate from
`RetryConfig.max_retries`, which handles transport or provider failures.

### map_reduce

| Parameter | Default | Meaning |
|---|---:|---|
| `map_prompt_template` | required | Must contain `{item}`. |
| `reduce_prompt_template` | required | Must contain `{mapped_outputs}`. |
| `max_concurrency` | `10` | Maximum map calls in flight. |
| `temperature` | `0.3` | Temperature for map and reduce calls. |
| `max_tokens` | `4096` | Maximum output tokens per call. |
| `max_cost` | `None` | Shared pattern budget. |
| `retry` | `None` | Uses `DEFAULT_RETRY`. |
| `trace` | `None` | No trace callback. |
| `stream` | `False` | `True` is rejected because the reduce step needs complete map results. |

The map phase is all-or-nothing. The reduce call starts only after every map
call succeeds.

### pipe

```text
pipe(provider, prompt, *steps, max_budget=None, **shared_kwargs)
```

`pipe()` filters shared keyword arguments against each step's signature.
`max_budget` is passed to each step as its remaining `max_cost`. A zero-step
pipe returns the original prompt with zero usage.

## Session defaults

```text
Kit(
    provider,
    *,
    track_cost: bool = True,
    messages = None,
    rate_limiter: TokenBucket | None = None,
)
```

`messages` is copied at construction. Only `turn()` reads and updates that
conversation history. Other Kit methods are single-shot calls.

The two streaming Kit methods each stream one model generation:

- `stream_consensus()` does not sample or vote;
- `stream_react_loop()` does not execute tools.

Usage on a streaming result is complete only after its text stream has been
fully consumed.

## Workflow and approval defaults

`Workflow` has no process-wide settings. It runs all currently ready steps as
one concurrent batch. `Workflow.run()` can receive an `initial_context`, a
checkpoint callback, or a checkpoint to resume.

`ApprovalGate` has no timeout unless `timeout_seconds` is set. Its default
timeout policy is `"raise"`. The other policies are `"deny"` and `"approve"`;
use `"approve"` only when fail-open behavior is an explicit application
requirement.

## Live evaluation environment

`live_provider_from_env()` returns `None` unless live evaluation is explicitly
enabled.

| Variable | Required | Purpose |
|---|---|---|
| `EXECUTIONKIT_LIVE_EVAL=1` | Yes, to enable | Opt in to live calls. |
| `EXECUTIONKIT_BASE_URL` | When enabled | OpenAI-compatible base URL. |
| `EXECUTIONKIT_MODEL` | When enabled | Provider model identifier. |
| `EXECUTIONKIT_API_KEY` | No | Defaults to an empty string. |

These variables configure only `live_provider_from_env()`. Normal
`Provider` construction does not read them.

## Installation extras

| Extra | Adds |
|---|---|
| `httpx` | Async HTTP transport; the base package falls back to `urllib`. |
| `jsonschema` | Full JSON Schema validation for tool arguments. |
| `otel` | OpenTelemetry API support for optional spans. |
| `dev` | Test, lint, type-check, coverage, and security-development tools. |
| `docs` | MkDocs and documentation plugins. |

See [Installation](../getting-started/installation.md) for commands.
