# Pattern API

This page renders signatures and docstrings from the current source. The
task-focused pages under [Patterns](../patterns/index.md) explain when to use
each function.

## Async patterns

### `consensus`

::: executionkit.patterns.consensus.consensus

### `refine_loop`

::: executionkit.patterns.refine_loop.refine_loop

### `react_loop`

::: executionkit.patterns.react_loop.react_loop

### `structured`

::: executionkit.patterns.structured.structured

### `pipe`

::: executionkit.compose.pipe

### `map_reduce`

::: executionkit.patterns.map_reduce.map_reduce

## Synchronous wrappers

The wrappers accept the same pattern-specific keyword arguments as their async
counterparts. They use `asyncio.run()` and therefore cannot run inside an
active event loop.

::: executionkit.consensus_sync

::: executionkit.refine_loop_sync

::: executionkit.react_loop_sync

::: executionkit.structured_sync

::: executionkit.pipe_sync

::: executionkit.map_reduce_sync

## Results and values

::: executionkit.types.PatternResult

::: executionkit.types.StreamingPatternResult

::: executionkit.types.TokenUsage

::: executionkit.types.Tool

::: executionkit.types.VotingStrategy

::: executionkit.types.TerminationReason

`Evaluator` is an async callable:

```text
Callable[[str, LLMProvider], Awaitable[float]]
```

It must return a finite score in the inclusive range `[0.0, 1.0]`.

`CheckpointCallback` receives an iteration index and a plain state dictionary.
It may be synchronous or async:

```text
Callable[[int, dict[str, Any]], Awaitable[None] | None]
```

`PatternStep` is the callable protocol accepted by `pipe()`:

```text
async def step(
    provider: LLMProvider,
    prompt: str,
    **kwargs: Any,
) -> PatternResult[Any]:
    ...
```

## Advanced helpers

Most applications should call a pattern or `Kit`. Custom pattern authors can
use the same completion, budget, retry, and trace path as built-in patterns:

::: executionkit.patterns.base.checked_complete

::: executionkit.patterns.base.checked_stream

::: executionkit.patterns.base.validate_score

::: executionkit.engine.json_extraction.extract_json

`checked_complete()` and `checked_stream()` require a caller-owned
`CostTracker`. Preserve the source ordering of the budget check and call
reservation: their no-`await` interval prevents concurrent asyncio tasks from
passing the same call-budget slot.
