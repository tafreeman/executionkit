# Configuration Reference

Every knob and its default. Grouped by component.

## Provider defaults

| Parameter | Default | Description |
|-----------|---------|-------------|
| `default_temperature` | `0.7` | Sampling temperature when not overridden per call. |
| `default_max_tokens` | `4096` | Per-completion token cap when not overridden. |
| `timeout` | `120.0 s` | HTTP request timeout. |

Per-call kwargs on `consensus`, `refine_loop`, `react_loop`, and `structured` always win over `Provider` defaults.

## RetryConfig

The default `DEFAULT_RETRY` is suitable for most workloads. Pass a custom `RetryConfig` to any pattern via `retry=`. See [Core → `RetryConfig`](core.md#executionkit.engine.retry.RetryConfig) for the full signature.

## ConvergenceDetector

Used internally by `refine_loop`. `delta_threshold`, `patience`, and `score_threshold` are surfaced as `refine_loop` parameters with the same names. See [Core → `ConvergenceDetector`](core.md#executionkit.engine.convergence.ConvergenceDetector).

## TokenUsage budgets

Pass a `TokenUsage` to `max_cost=` (single pattern) or `max_budget=` (`pipe`). Field convention:

| Value | Meaning |
|-------|---------|
| `0` | "No limit" — the field is unbounded. |
| `> 0` | Tokens / calls remaining. |
| `-1` | Field was bounded and is now exhausted. (Used internally by `pipe` to forward exhausted budgets without aliasing them as "unlimited".) |

```python
from executionkit import TokenUsage, consensus

# Cap at 5K input tokens, 2K output tokens, 10 LLM calls
budget = TokenUsage(input_tokens=5_000, output_tokens=2_000, llm_calls=10)

result = await consensus(provider, "...", num_samples=5, max_cost=budget)
```

## Pattern parameter cheat sheet

### `consensus`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `num_samples` | `5` | Must be `>= 1`. |
| `strategy` | `"majority"` | Or `"unanimous"`. |
| `temperature` | `0.9` | Higher = more diverse. |
| `max_tokens` | `4096` | Per completion. |
| `max_concurrency` | `5` | Semaphore for parallel calls. |
| `retry` | `DEFAULT_RETRY` | Per-call. |
| `max_cost` | `None` | Shared across all samples. |

### `refine_loop`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `evaluator` | `None` | `async (text, provider) -> float in [0,1]`. |
| `max_eval_chars` | `32_768` | Default-evaluator truncation. |
| `target_score` | `0.9` | Convergence target. |
| `max_iterations` | `5` | Excludes initial generation. |
| `patience` | `3` | Stale-delta iterations before stopping. |
| `delta_threshold` | `0.01` | Minimum meaningful improvement. |
| `temperature` | `0.7` | Generation temp; evaluator uses `0.1`. |
| `max_tokens` | `4096` | Per completion. |
| `max_cost` | `None` | Across all calls. |
| `retry` | `DEFAULT_RETRY` | Per-call. |

### `react_loop`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `max_rounds` | `8` | Raises `MaxIterationsError` when hit. |
| `max_observation_chars` | `12_000` | Per tool result. |
| `tool_timeout` | `None` | Falls back to `Tool.timeout` (`30.0 s`). |
| `temperature` | `0.3` | Lower = more deterministic tool selection. |
| `max_tokens` | `4096` | Per completion. |
| `max_cost` | `None` | Across all rounds. |
| `retry` | `DEFAULT_RETRY` | Per-call. |
| `max_history_messages` | `None` | When set, trims history; always preserves the original prompt. |

### `structured`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `validator` | `None` | Optional callable that accepts parsed JSON or returns an error string / `False`. |
| `max_retries` | `3` | Repair attempts after the first parse. Must be `>= 0`. |
| `temperature` | `0.0` | Lower = more deterministic JSON. |
| `max_tokens` | `4096` | Per completion. Must be `>= 1`. |
| `max_cost` | `None` | Across the initial call and repairs. |
| `retry` | `DEFAULT_RETRY` | Per-call transport retry config. |

### `pipe`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `*steps` | — | Async pattern callables. |
| `max_budget` | `None` | Forwarded to each step as `max_cost=`. |
| `**shared_kwargs` | — | Filtered to each step's signature. |

## Tool defaults

```python
@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: Mapping[str, Any]                # JSON Schema
    execute: Callable[..., Awaitable[str]]
    timeout: float = 30.0
```

`Tool.timeout` applies per-call. Override per pattern call with `react_loop(..., tool_timeout=N)`.

## Environment variables

ExecutionKit reads no environment variables of its own. All configuration is explicit per `Provider` instance. Read `os.environ` in your application code.

The default `Provider` does respect:

- `HTTP_PROXY`, `HTTPS_PROXY` — when using the `httpx` backend, these are picked up via `httpx.AsyncClient` defaults.

## Coverage and quality gates

Project-level CI gates (in `pyproject.toml`):

| Gate | Threshold |
|------|-----------|
| `pytest --cov-fail-under` | **80%** |
| `mypy --strict` | Zero errors. |
| `ruff check` rules | `E F W I N UP S B A C4 SIM TCH RUF`. |
| `bandit` | No HIGH severity findings. |
