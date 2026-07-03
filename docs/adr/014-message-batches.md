# ADR-014: Anthropic Message Batches fan-out via stdlib HTTP

- Status: accepted
- Date: 2026-07-03
- Decision-makers: maintainer

## Context and problem statement

ExecutionKit's fan-out patterns (`consensus`, `map_reduce`) run N live,
concurrent calls against an OpenAI-compatible endpoint. For large sample
counts and offline map-reduce jobs, a provider-side batch API is the better
transport: one submission, asynchronous processing, results collected when
the batch ends — at substantially lower per-token cost and with no
client-side concurrency management. Anthropic's Message Batches API
(`POST /v1/messages/batches`) offers exactly this, but it is not part of the
OpenAI-compatible dialect the rest of the library speaks, and the obvious
implementation path (the `anthropic` SDK) violates the zero-runtime-
dependency stance (ADR-004).

## Decision drivers

- ADR-004: zero runtime dependencies must survive.
- One voting semantics: a batch-backed consensus must decide winners exactly
  like the live `consensus` pattern, or "consensus" means two different
  things depending on transport.
- Honest failure behaviour: a batch entry that errored/expired must not be
  silently dropped from an aggregate.
- The OpenAI-compatible `Provider` abstraction must not be contorted to
  pretend batching is dialect-neutral.

## Considered options

1. **Stdlib `urllib` client + native Anthropic endpoint, separate module** —
   chosen.
2. `anthropic` SDK as an optional extra (`executionkit[anthropic]`) — the
   SDK is well-typed, but the Batches surface used here is three small HTTP
   calls; an extra dependency (and its transitive httpx pin) buys little.
3. Extend `Provider` with batch methods — rejected: `Provider` models the
   OpenAI `/chat/completions` dialect, which has no inline-JSON batch
   analog (OpenAI's Batch API is file-upload based). Forcing both dialects
   through one abstraction would leak vendor specifics into every provider.

## Decision outcome

Option 1: a self-contained `executionkit/batches.py` with

- `AnthropicBatchClient` — three async calls (`create_batch`, `get_batch`,
  `fetch_results`) over stdlib `urllib` in a worker thread. All transport
  goes through a single seam (`_http_raw`) so tests run entirely offline.
  The `x-api-key` credential is attached as an *unredirected* header,
  mirroring `Provider._post_urllib`'s protection against credential leakage
  on cross-host redirects. The `anthropic-version` header is pinned
  (`2023-06-01`).
- `consensus_batch()` — N identical prompts as one batch, scored by the
  same `tally_votes` the live pattern uses. To guarantee that, the voting
  logic was **extracted** from `patterns/consensus.py` into
  `engine/voting.py` and both transports import it — one implementation,
  two transports.
- `map_batch()` — one request per prompt, results returned in prompt order
  regardless of completion order; the "map" half of a map-reduce.
- Strict all-or-nothing failure: any non-`succeeded` entry raises
  `ProviderError` naming the failed `custom_id`s (mirrors `gather_strict`
  in the live fan-out). HTTP 429 maps to `RateLimitError` with
  `retry_after`; polling is bounded by a configurable wall-clock timeout.

Both helpers return the standard `PatternResult` with summed `TokenUsage`
(`llm_calls` = batch entries) and a `batch_id` metadata key.

## Consequences

- Good: zero-dep stance intact; batch and live consensus provably share
  voting; tests never touch the network.
- Good: cost-sensitive fan-outs get a provider-discounted path without any
  new dependency.
- Bad: Anthropic-specific — a second vendor dialect now exists in the
  codebase, explicitly quarantined to this module. An OpenAI Batch API path
  would be a separate ADR (file-upload lifecycle, different enough not to
  share this client).
- Bad: polling is simple interval-based; no webhook support. Acceptable for
  the offline workloads this targets.
- Neutral: the live `consensus()` remains the right choice for
  latency-sensitive interactive use; docs state the trade explicitly.
