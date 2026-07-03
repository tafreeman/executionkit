# ADR-015: react_loop tool-execution sandbox contract

- Status: accepted
- Date: 2026-07-03
- Decision-makers: maintainer

## Context and problem statement

`react_loop` executes developer-registered async callables chosen by the
model. The model controls *which* tool runs, with *what arguments*, and *how
many* calls a round requests — so the execution harness, not the tools, is
the security/reliability boundary. The 2026-07-01 portfolio audit flagged
"tool sandbox for react_loop callables" as a gap (G4), with a pointer to
review ARP's ADR-024 (pure-AST expression interpreter, eliminating `eval()`)
for reuse before writing new code.

## Review of ARP ADR-024 (the reuse pointer)

ADR-024 solves a different layer: interpreting *model-influenced expression
strings* without `eval()`/`compile()`. ExecutionKit has exactly one place
where model-influenced text is evaluated as an expression — the MCP demo
calculator (`executionkit/mcp/_demo_tools.py`) — and it already implements
the ADR-024 approach: `ast.parse` + node/operator allowlist dispatched
through the `operator` module, no `eval()` anywhere in the package. Nothing
further to port: EK's tools are developer-written Python callables, not
interpreted strings, so an AST interpreter is not the boundary here.

## What the execution harness already enforced (verified against live code)

The audit-time gap was narrower than its title. As of this ADR,
`_execute_tool_call` / `_execute_tool_calls_round` already provided:

- **Argument validation before execution** — a strict stdlib subset
  validator (required keys, additionalProperties, primitive types), upgraded
  to full JSON Schema when the optional `jsonschema` extra is installed;
  invalid arguments become an error observation, the tool never runs.
- **Per-call timeout** — `asyncio.wait_for` with a per-`Tool` default and a
  loop-level override; a hung tool becomes a bounded error observation.
- **Exception isolation** — a raising tool never propagates; the observation
  carries only the exception *type* (messages/tracebacks can contain
  arguments, URLs, credentials) and logging is similarly redacted.
- **Output bounding** — observations truncate at `max_observation_chars`.
- **Human gate** — an optional `ApprovalGate` checked per call; denials
  become observations, and the gate itself fails closed (ADR-010 lineage).
- **Trace redaction** — `tool_call_start` events emit argument keys only by
  default.
- **Bounded iteration** — `max_rounds` caps think-act-observe cycles.

## The genuine gap and decision

One hole remained: a round's tool calls all run **concurrently** and the
number of calls per round was unbounded — a buggy or adversarial model
requesting hundreds of calls in one turn produced an unbounded concurrent
fan-out (resource exhaustion; amplified damage if tools have side effects).

Decision: add `max_tool_calls_per_round` (default
`_DEFAULT_MAX_TOOL_CALLS_PER_ROUND = 32`, validated `>= 1`). Calls beyond
the cap are **never executed**; each still receives a tool-role rejection
observation (every `tool_call_id` in the transcript must be answered for the
conversation to stay well-formed) telling the model to retry with fewer, and
is counted in new `rejected_tool_calls` metadata.

Alternatives considered:

- Reject the whole round — harsher than needed; executing the first N in
  request order is deterministic and lets partial progress stand.
- A concurrency semaphore without a count cap — bounds parallelism but not
  total work per round; the count cap bounds both.
- OS-level isolation (subprocess/container per tool) — out of scope for a
  zero-dependency library; tools are developer-trusted code, and callers
  needing process isolation can implement it inside their `Tool.execute`.

## Consequences

- Good: the sandbox contract is now complete and documented in one place
  (this ADR + the README "Tool execution sandbox" section); the fan-out is
  bounded end-to-end (rounds × calls-per-round × per-call timeout ×
  observation size).
- Good: no behavior change for real workloads (models rarely exceed ~10
  parallel calls; the default cap is 32).
- Neutral: the cap is per-round, not per-run; `max_rounds` already bounds
  the run dimension.
- Explicit non-goal: EK does not sandbox the *Python* inside a tool —
  tools are the developer's code. The boundary defended here is the
  model→harness edge, and (per the ADR-024 review) the only interpreted
  model text in the package already runs on a pure-AST interpreter.
