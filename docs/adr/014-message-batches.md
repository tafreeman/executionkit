# ADR-014: Keep Anthropic Message Batches separate from live patterns

- Status: Accepted
- Date: 2026-07-03

## Context

Large offline fan-out jobs can use Anthropic's native Message Batches API, whose
submission and polling flow differs from OpenAI-compatible live completions.

## Decision

Provide a standard-library `AnthropicBatchClient` plus `consensus_batch()` and
`map_batch()`. Submit a batch, poll until it ends, fetch JSONL results, restore
request order by `custom_id`, and fail the operation if any entry did not
succeed.

Reuse the same vote tallying as live consensus. Report returned token totals
and set `llm_calls` to the number of batch entries, not the number of polling
requests.

## Consequences

- Batch and live execution have separate, explicit transports.
- Callers choose the model, polling interval, and completion timeout.
- Partial batch success is not returned silently.
- The client supports this bounded Anthropic API only; it is not a native
  provider adapter for normal patterns.

## Rejected alternatives

Pretending batches use the chat-completions interface would hide incompatible
request and lifecycle semantics. Adding a provider SDK would conflict with the
base-install decision.
