# ADR-016: Reach a Claude subscription through the Agent SDK, in an extra

- Status: Accepted
- Date: 2026-08-19

## Context

Both existing transports authenticate with an API key: `Provider` sends one to
an OpenAI-compatible `/chat/completions` endpoint, and `AnthropicBatchClient`
sends one as `x-api-key`. An operator who pays for a Claude subscription rather
than API credits cannot use either — the library is unreachable to them without
separately buying API access.

Subscription credentials are not an environment variable. They live in the
Claude Code CLI's own credential store, and the only supported way to spend them
programmatically is `claude-agent-sdk`, which drives that CLI. There is no
endpoint, header, or token format we could speak over `urllib` to get the same
effect, so ADR-003's "one OpenAI-compatible provider" and ADR-014's stdlib
client do not stretch to cover this case.

That collides with ADR-004. ADR-014 stated the position plainly: "Adding a
provider SDK would conflict with the base-install decision."

## Decision

Add `ClaudeAgentProvider` in `executionkit/claude_sdk.py`, satisfying the
existing `LLMProvider` and `StreamingProvider` protocols, and gate
`claude-agent-sdk` behind a `[claude]` extra.

ADR-004 is unchanged and not superseded: the base install stays dependency-free.
This is the same shape already used for `httpx`, `jsonschema`, and OpenTelemetry
— an opt-in extra that the core never imports. The distinction ADR-014 drew
still holds for the transports it governed; the exception here is bought by the
fact that no stdlib implementation exists at any price, not by convenience.

Do not emulate the controls the harness lacks. `ClaudeAgentOptions` has no
sampling temperature and no output-token ceiling, so `temperature` and
`max_tokens` warn rather than being quietly dropped, and the harness's own
knobs (`effort`, `thinking`, `max_budget_usd`) are exposed instead.

Do not claim tool support. The Agent SDK executes its own tools rather than
returning tool calls for the caller to run, which inverts `react_loop`'s
contract, so the class does not set `supports_tools` and the existing
capability check rejects it before a loop starts.

Scrub the API-key environment variables from the CLI subprocess. The SDK spawns
the CLI with `{**os.environ, **options.env}`, so a process holding
`ANTHROPIC_API_KEY` — which any process using `AnthropicBatchClient` does —
would hand the child that key and the CLI would authenticate with it. That is a
silent credential-class switch: the call bills the API account rather than the
subscription, and fails outright when the key is invalid or unfunded, which is
the exact opposite of what a transport named for subscription auth should do.
Blanked rather than removed, because `options.env` merges over `os.environ` and
so can only override, never unset; the CLI treats an empty value as absent.
Caller-supplied `env` applies last, so deliberate API-key billing stays
available to anyone who asks for it explicitly.

Keep `claude-agent-sdk` out of the `dev` extra. It depends on `mcp`, which
depends on `opentelemetry-api`; locking it into `dev` would put OpenTelemetry
into the `test` job and silently destroy the property that job exists to prove.
The transport's tests skip without the extra, and a dedicated `claude-sdk` CI
job installs it and hard-guards the import — the same split ADR-010's
OpenTelemetry work established.

## Consequences

- Subscription holders can run every provider-agnostic pattern with no API key.
- The base install is still dependency-free; `pip install executionkit` is
  unchanged, and nothing in the core imports the SDK.
- The extra carries a prerequisite pip cannot express: the Claude Code CLI must
  be installed and signed in. A missing CLI surfaces as `PermanentError` with
  that instruction rather than a transport error.
- `consensus()` over this transport is weaker evidence than over `Provider`,
  because its sample diversity normally comes from temperature. This is
  documented at the call site rather than hidden.
- `react_loop()` is unavailable over this transport.
- A process that holds both a subscription and an API key gets the subscription
  from this transport unless it says otherwise. That is the intended default —
  the class is named for it — but it does mean the credential class is a
  property of the transport rather than of ambient environment.
- Subscription rate-limit windows are a new failure mode; rejected windows map
  to `RateLimitError` with a `retry_after` derived from the reported reset.

## Rejected alternatives

Speaking to the subscription over raw `urllib`, as `batches.py` does, would
preserve zero dependencies but is not possible: the credential exchange is
internal to the CLI and has no documented wire contract to reimplement. Doing so
anyway would mean reverse-engineering a private surface that can change without
notice.

Requiring an API key from subscription holders — the status quo — keeps the
dependency story clean by making the library unusable for that entire class of
operator.

Adding `anthropic` (the API SDK) instead would reach the Messages API with full
sampling and tool-schema support, but it authenticates with an API key or an
`ant auth login` profile. Neither is the subscription sign-in, so it solves a
different problem; it remains the right choice if API-key parity ever matters
more than subscription reach.
