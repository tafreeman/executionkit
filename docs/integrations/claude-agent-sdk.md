# Claude Agent SDK (subscription sign-in)

`ClaudeAgentProvider` runs ExecutionKit's provider-agnostic patterns against
Claude using a **Claude subscription sign-in** instead of an API key. It is the
only transport in the library that does not need `ANTHROPIC_API_KEY` or an
OpenAI-compatible endpoint.

See [ADR-016](../adr/016-claude-agent-sdk-transport.md) for why an SDK dependency
is admitted here when [ADR-004](../adr/004-zero-runtime-dependencies.md) keeps
the base install dependency-free.

## Install

```bash
pip install 'executionkit[claude]'
```

The extra also needs the Claude Code CLI on `PATH`, signed in once:

```bash
claude
```

That prerequisite is a machine-level one that pip cannot express. If the CLI is
missing, the provider raises `PermanentError` with the install instruction
rather than a transport error.

Credentials are resolved entirely by the CLI. ExecutionKit never reads, stores,
or forwards them.

### If your process already has an API key

The SDK spawns the CLI with `{**os.environ, **options.env}`, so a process that
has `ANTHROPIC_API_KEY` set — which any process using `AnthropicBatchClient`
does — would hand the child that key, and the CLI would authenticate with it.
That is a silent credential-class switch: the call bills the API account
instead of the subscription, and fails outright when the key is invalid or
unfunded.

`ClaudeAgentProvider` therefore blanks `ANTHROPIC_API_KEY` and
`ANTHROPIC_AUTH_TOKEN` in the CLI subprocess. They are blanked rather than
removed because `options.env` merges *over* `os.environ` and can only override
a key, never unset it; the CLI treats an empty value as absent.

To deliberately bill an API key instead, say so explicitly — the constructor's
`env` is applied over the scrub:

```python
provider = ClaudeAgentProvider(env={"ANTHROPIC_API_KEY": "sk-ant-..."})
```

## Use

```python
import asyncio

from executionkit import ClaudeAgentProvider, consensus

provider = ClaudeAgentProvider(model="claude-opus-5", effort="high")

result = asyncio.run(
    consensus(provider, "Is 1024 a power of two? Answer yes or no.", num_samples=3)
)
print(result.value)
```

`ClaudeAgentProvider` satisfies `LLMProvider` and `StreamingProvider`, so it
drops into `consensus()`, `refine_loop()`, `map_reduce()`, `structured()`,
`pipe()`, `Kit`, and the streaming helpers the same way `Provider` does.

## What this transport cannot do

The Agent SDK is an agent harness, not a raw completions endpoint. Three
controls have no equivalent, and the provider surfaces that rather than
pretending otherwise.

| ExecutionKit input | Behaviour | Use instead |
|---|---|---|
| `temperature` | Warns; no sampling control exists | `effort` |
| `max_tokens` | Warns; the harness bounds by turns and spend | `max_budget_usd` |
| `tools` | Raises `PermanentError` | `Provider` for `react_loop()` |

Two consequences worth planning around:

- **`consensus()` is weaker evidence here.** Its sample diversity normally comes
  from temperature. Over this transport the samples vary only by the model's own
  nondeterminism, so a unanimous vote says less than the same vote over
  `Provider`.
- **`react_loop()` is unavailable.** The Agent SDK executes its own tools rather
  than returning tool calls for the caller to run, which is the inverse of what
  `react_loop()` needs. The provider does not set `supports_tools`, so
  `react_loop()` rejects it up front instead of failing mid-loop.

## Harness controls

Constructor arguments map onto the SDK's own knobs:

| Argument | Effect |
|---|---|
| `model` | Claude model id (default `claude-opus-5`) |
| `system_prompt` | Prepended ahead of any `system` turn in `messages` |
| `effort` | `low` \| `medium` \| `high` \| `xhigh` \| `max` |
| `thinking` | Extended-thinking config, passed through verbatim |
| `max_budget_usd` | Hard per-call spend ceiling |
| `max_turns` | Turn ceiling; `1` keeps the harness to a single completion |
| `cwd` | Working directory handed to the CLI |
| `env` | Extra CLI-subprocess environment, applied over the API-key scrub |
| `extra_options` | Escape hatch merged into `ClaudeAgentOptions` |

Every call is issued with an empty tool set and an empty allow-list, so a
completion has no filesystem, shell, or network side effects.

## Message translation

ExecutionKit speaks OpenAI-style `messages`; the harness takes a prompt plus a
system prompt. `system` turns are hoisted into `system_prompt`. A lone user turn
is passed through verbatim; a genuine multi-turn history is rendered as a
labelled transcript, because the SDK's streaming-input mode accepts only *user*
messages and a prior assistant turn has no lossless representation.

## Usage and cost

`LLMResponse` already understands Anthropic's `input_tokens` / `output_tokens`
spelling, so token counts pass through unchanged. The harness-reported
`total_cost_usd` is added to `usage` and set on the OpenTelemetry span when the
`[otel]` extra is installed.

## Rate limits

Subscription rate-limit windows are a failure mode API keys do not have. A
rejected window raises `RateLimitError` with `retry_after` derived from the
reported reset time, so the standard retry configuration handles it. Warning-level
windows (`allowed_warning`) pass through without interrupting the call.
