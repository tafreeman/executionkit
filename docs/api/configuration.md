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
| `trace` | `None` | Optional `TraceCallback`. |

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
| `trace` | `None` | Optional `TraceCallback`. |

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
| `trace` | `None` | Optional `TraceCallback`. |
| `approval_gate` | `None` | Optional `ApprovalGate` checked before each tool body is executed. |

### `structured`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `validator` | `None` | Optional callable that accepts parsed JSON or returns an error string / `False`. |
| `max_retries` | `3` | Repair attempts after the first parse. Must be `>= 0`. |
| `temperature` | `0.0` | Lower = more deterministic JSON. |
| `max_tokens` | `4096` | Per completion. Must be `>= 1`. |
| `max_cost` | `None` | Across the initial call and repairs. |
| `retry` | `DEFAULT_RETRY` | Per-call transport retry config. |
| `trace` | `None` | Optional `TraceCallback`. |

### `Workflow`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | — | Sequence of named `Step` objects with optional dependencies. |
| `initial_context` | `None` | Mapping copied into the workflow output context before steps run. |
| `trace` | `None` | Optional `TraceCallback` for `workflow_step_*` events. |
| `approval_gate` | `None` | Optional `ApprovalGate` checked before each step. |

### `Plan`

| Parameter | Default | Notes |
|-----------|---------|-------|
| `steps` | — | Ordered sequence of named `PlanStep` objects. |
| `initial_context` | `None` | Mapping copied into the plan output context before steps run. |
| `trace` | `None` | Optional `TraceCallback` for `plan_step_*` events. |
| `approval_gate` | `None` | Optional `ApprovalGate` checked before each step. |

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

Most ExecutionKit configuration is explicit per `Provider` instance. Read `os.environ` in your application code for normal provider setup.

The default `Provider` does respect:

- `HTTP_PROXY`, `HTTPS_PROXY` — when using the `httpx` backend, these are picked up via `httpx.AsyncClient` defaults.

The eval helper `live_provider_from_env()` reads these opt-in variables:

| Variable | Meaning |
|----------|---------|
| `EXECUTIONKIT_LIVE_EVAL` | Must be `1` to enable live eval provider construction. |
| `EXECUTIONKIT_BASE_URL` | Required base URL for the OpenAI-compatible endpoint. |
| `EXECUTIONKIT_MODEL` | Required model name. |
| `EXECUTIONKIT_API_KEY` | Optional API key. |

## Eval suite

Beyond code coverage, ExecutionKit ships an **output-correctness** eval suite that runs offline in CI:

- **Golden suite** (`tests/eval_datasets.py` → `golden_cases()`): deterministic per-pattern goldens (structured extraction, consensus voting, refine best-not-last, ReAct tool calls) that assert exact values *and* metadata through a `MockProvider`.
- **Failure corpus** (`tests/eval_failure_cases.py`): curated malformed-output, prompt-injection, and bad-tool-argument cases proving each is handled gracefully (repair, blocked execution, `ProviderError`) rather than crashing.
- **Accuracy metrics**: `EvalReport.accuracy` and `EvalReport.summary()` report pass-rate, not just pass/fail — e.g. `7/9 passed (77.8% accuracy)`.
- **Opt-in live tiers** (`tests/test_judge_calibration.py`, `tests/test_live_regression.py`): judge-calibration and per-pattern regression against a real OpenAI-compatible endpoint, skipped unless `EXECUTIONKIT_LIVE_EVAL=1` (see the table above).

The deterministic tiers run as a dedicated **Eval suite** CI step on every push; the live tiers stay env-gated so normal CI never needs a network or a key. A separate **Live Eval** workflow (`.github/workflows/live-eval.yml`, manual `workflow_dispatch` + weekly) runs the live tiers against a local Ollama model and uploads the results as a `live-eval-results.xml` artifact — real-endpoint evidence without blocking any PR.

## Coverage and quality gates

Project-level CI gates (in `pyproject.toml`):

| Gate | Threshold |
|------|-----------|
| `pytest --cov-fail-under` | **80%** |
| `mypy --strict` | Zero errors. |
| `ruff check` rules | `E F W I N UP S B A C4 SIM TCH RUF`. |
| `bandit` | No HIGH severity findings. |
| Eval suite (goldens + failure corpus) | All cases pass. |
