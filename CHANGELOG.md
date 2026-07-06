# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Add multi-turn conversation primitives. `react_loop` now accepts `messages=` (a prior conversation to continue, mutually exclusive with `prompt`) and returns the full updated transcript as `metadata["messages"]`, so callers can thread state across turns
- Add `Kit.turn(user_text, tools=...)` plus a `Kit.messages` transcript (and an optional `messages=` seed on `Kit`), giving a stateful conversational API on top of `react_loop`
- Add message-construction helpers `system_message`, `tool_message`, and `assistant_tool_calls_message` to `executionkit.engine.messages`
- Add `examples/conversational_assistant.py` demonstrating multi-turn tool use with context carryover
- Add a multi-turn eval harness — `ConversationScript`, `Turn`, and `run_conversation_script(script, kit)` — that drives a scripted conversation through a single `Kit` (state carries across turns) and returns an `EvalReport`, one result per turn
- Add optional rate limiting to `Kit` via a `rate_limiter: TokenBucket | None` parameter; a token is acquired before every pattern dispatch
- Add an optional `summarizer=` hook to `react_loop` that compresses history dropped by `max_history_messages` trimming into a system note for the active window (the stored transcript is unchanged); a `summarized` count is reported in metadata
- `react_loop` checkpoint state now includes the running `messages` transcript, enabling conversation-level resume
- Add a "Building a conversational assistant" recipe (`docs/recipes/assistant.md`) covering stateful turns, `structured()` intent/slot NLU, the streaming limitation, and `ConversationScript` evals
- Add the `map_reduce()` pattern — parallel fan-out over a collection of inputs, each processed independently, then reduced to a single answer (ADR-011)
- Add a stdlib-only MCP server — `python -m executionkit.mcp` speaks newline-delimited JSON-RPC 2.0 over stdio and exposes `consensus` and a demo-toolset-restricted `react_loop` as MCP tools (ADR-012)
- Add Anthropic Message Batches fan-out — `consensus_batch()` and `map_batch()` submit samples as a single batch job over a stdlib `urllib` client and score with the same `tally_votes` as the live `consensus()` pattern (ADR-014)

### Changed

- `react_loop()` no longer silently swallows unknown keyword arguments (the `**_` sink was removed); an unsupported kwarg now raises `TypeError`. `prompt` is now optional (defaults to `None`) and `tools` defaults to `()` **(behavior change)**

## [0.2.0] - 2026-06-08

### Added

- Add lightweight orchestration primitives: `Router`/`RouteRule` for provider selection before a pattern call, `Workflow`/`Step` for dependency-ordered async fan-out, and `Plan`/`PlanStep` for ordered plan-then-act execution
- Add approval gates — `ApprovalGate`, `ApprovalRequest`, `ApprovalDecision`, and `ApprovalDeniedError` — that require human or policy approval before tool execution, workflow steps, or plan steps; wired into `react_loop` (a denial becomes a tool observation) and into `Workflow`/`Plan` (a denial aborts)
- Add observability hooks — `TraceEvent`, `TraceCallback`, and `emit_trace` — emitting structured sync-or-async events for LLM call start/end/error, tool calls, workflow steps, plan steps, and approvals; add a `trace=` parameter to `consensus`, `refine_loop`, `react_loop`, and `structured`
- Add an eval harness — `EvalCase`, `EvalResult`, `EvalReport`, and `run_eval_suite()` for deterministic golden checks, plus `live_provider_from_env()` for opt-in live evals gated on `EXECUTIONKIT_LIVE_EVAL`; `EvalReport` reports `accuracy` and `summary()`
- Add an output-correctness eval suite: deterministic per-pattern golden datasets and a curated model-failure corpus that run offline in CI under a dedicated "Eval suite" gate, plus opt-in judge-calibration and per-pattern live-provider regression tiers and a scheduled/manual `Live Eval` workflow that runs them against a local Ollama model
- Add an `approval_gate=` parameter to `react_loop`, `Workflow.run`, and `Plan.execute`

### Changed

- Budget accounting now counts every dispatched wire attempt — including failed retries — toward `llm_calls`, and the dead `release_call()` slot-release path was removed; a `max_cost` `llm_calls` ceiling now caps total attempts, not just successes **(behavior change)**
- `Router.run(pattern, prompt, *, context=..., **kwargs)` takes routing inputs through an explicit `context` mapping disjoint from the pattern's keyword arguments, so a routing key (e.g. `tier`) can no longer leak into the pattern call and raise `TypeError`
- Broaden credential redaction to match common keyless token shapes (`ghp_`/`gho_`, `AIza`, `xox[bpoa]-`, `gsk_`, and `key=`/`token:`/`bearer …` variants) and apply it to transport-failure messages and malformed tool-argument echoes as well as HTTP error bodies

### Security

- Harden the `refine_loop` default judge: embedded `</response_to_rate>` envelope tags are stripped from candidate text so adversarial content cannot break out of the scoring sandbox
- Bounds-check provider-reported token usage (`_usage_int`): reject booleans, negatives, and absurdly large counts as `ProviderError` so a hostile or buggy endpoint cannot under-count and bypass `max_cost`
- Add `ApprovalGate` as an opt-in control for human/policy review before tool, workflow, or plan side effects

### Fixed

- Map urllib read-phase `TimeoutError` to a retryable `ProviderError` on the default (no-`httpx`) transport path, matching the `httpx` backend
- `Kit.usage` now records the partial cost carried by a raised `ExecutionKitError` (e.g. `BudgetExhaustedError`, `MaxIterationsError`) instead of dropping it when a pattern aborts
- Harden `Router.run` against a `prompt` key in the routing context colliding with the positional `prompt` argument to `select()`
- Strengthen ReAct history-trimming tests (remove `asyncio.coroutine`, unavailable since Python 3.11) and assert on `rounds`/`tool_calls_made`/`truncated_observations`/`messages_trimmed` metadata

## [0.1.0] - 2026-05-22

### Security

- Fix prompt injection in `refine_loop` default evaluator via XML delimiter sandboxing and input truncation to 32 768 chars
- Mask API key in `Provider.__repr__` — previously leaked `sk-...` values in logs and tracebacks
- Redact credential-pattern substrings from HTTP error messages using `_redact_sensitive` regex
- Return only exception type name (not message) from tool error handler in `react_loop` to prevent leaking internal details to the LLM
- Add Bandit SAST job to CI and Dependabot weekly auto-update configuration for pip and GitHub Actions

### Added

- Add the `structured()` pattern and `structured_sync()` wrapper for JSON extraction, optional validation, and repair retries
- Add optional `httpx` backend for HTTP connection pooling — install with `pip install executionkit[httpx]`; falls back to `urllib` when `httpx` is absent
- Add `max_history_messages: int | None` parameter to `react_loop` for capping message history size; always preserves the original user prompt
- Add `_validate_tool_args` helper in `react_loop` that validates tool call arguments against JSON Schema (required fields, `additionalProperties`, and type checks) before execution — uses stdlib only, no `jsonschema` dependency
- Add `aclose()` and async context manager support (`__aenter__`/`__aexit__`) to `Provider` for explicit HTTP client lifecycle management
- Add `messages_trimmed` counter to `react_loop` metadata
- Add MkDocs Material documentation site with public guides for installation, provider setup, patterns, recipes, API reference, contributing, license, and changelog
- Add architecture decision records for structural protocols, flat package layout, and single OpenAI-compatible provider design
- Add GitHub Pages documentation deployment workflow and CodeQL analysis workflow
- Add supply-chain hardening with `requirements.lock` and SBOM artifact generation in the publish workflow

### Fixed

- Fix `consensus` voting incorrectly splitting semantically identical responses that differ only in trailing newlines or internal whitespace — votes now use normalized text while the original winning response is preserved
- Fix `_parse_score` silently accepting scores outside the 0–10 range; now raises `ValueError` for out-of-range values
- Remove phantom `pydantic>=2.0` from `project.dependencies`; pydantic was never imported in the library source
- Fix strict MkDocs builds by excluding internal documents with stale cross-references from the public site

### Changed

- Change `PatternResult.metadata` type from `dict[str, Any]` to `MappingProxyType[str, Any]` to enforce true immutability on a frozen dataclass
- Update GitHub Actions workflow dependencies to current major versions
- Replace the old Astro documentation site with the MkDocs Material site
