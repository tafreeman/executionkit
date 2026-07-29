# Evaluation API

## Single-run cases

::: executionkit.evals.EvalCase

::: executionkit.evals.EvalResult

::: executionkit.evals.EvalReport

::: executionkit.evals.run_eval_suite

## Conversation scripts

::: executionkit.evals.Turn

::: executionkit.evals.ConversationScript

::: executionkit.evals.run_conversation_script

## Live-provider helper

::: executionkit.evals.live_provider_from_env

`live_provider_from_env()` reads:

| Variable | Required when enabled |
|---|---|
| `EXECUTIONKIT_LIVE_EVAL=1` | Enables construction. |
| `EXECUTIONKIT_BASE_URL` | Yes |
| `EXECUTIONKIT_MODEL` | Yes |
| `EXECUTIONKIT_API_KEY` | No |

It returns `None` when live evaluation is not enabled. It raises `ValueError`
when the flag is enabled but a required value is missing.

Read the [Evaluation guide](../guides/evaluation.md) for examples and the
difference between repeatable and live checks.
