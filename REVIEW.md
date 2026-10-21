# REVIEW.md
<!-- Read by the AI reviewer from the BASE branch only. Byte-stable. Owner: @tafreeman. Changes route to high_risk. -->

## What this repo is
ExecutionKit is an async Python library of LLM call patterns (consensus, refine loop, ReAct tool loop, structured output, map-reduce), plus cost tracking, approval gates, routing, workflows, evals, and a small stdio MCP server. The core runs on the standard library only and talks to OpenAI-compatible endpoints. It is published to PyPI and imported by other repos.

## Invariants a change must not break
- The base install has no runtime dependencies; extras (`httpx`, `jsonschema`, `otel`, `claude`) are optional with a defined fallback — `pyproject.toml` `dependencies = []`, ADR-004. Checked: `ci.yml` `test` job installs only `requirements.lock` plus `-e . --no-deps`, and `observability`/`claude-sdk` jobs cover the extras. Nothing asserts the list stays empty.
- `requirements.lock` matches the dev extra — `scripts/check_lock_parity.py`. Checked: `ci.yml` `test` job.
- Public exports and docs match the source tree — `executionkit/__init__.py`, `docs/`. Checked: `scripts/check_doc_facts.py` and `tests/test_exports.py`, in `ci.yml` `test` job.
- Approval timeout defaults to `"raise"`; `"approve"` is fail-open and must stay explicit — `executionkit/approval.py`, ADR-009. Checked: `tests/test_approval.py`.
- Provider error text and `repr` never expose credentials — `executionkit/provider.py` (`_redact_sensitive`, `Provider.__repr__`). Checked: `tests/test_provider.py`.
- The Agent SDK transport never reads, stores or forwards an API key; the CLI subprocess cannot inherit one — `executionkit/claude_sdk.py`, ADR-016. Checked: `tests/test_claude_sdk.py`, `ci.yml` `claude-sdk` job.
- `react_loop` validates before running a tool: duplicate names, per-round call cap, schema, approval, timeout, truncated output, redacted trace args — `executionkit/patterns/`, ADR-015. Checked: `tests/patterns/`.
- Value types are frozen and metadata is a read-only mapping (`MappingProxyType`) — `executionkit/types.py`. Checked: `tests/test_types.py`.
- `executionkit.patterns.base._TrackedProvider` keeps the shape agentic-runtime-platform imports — Checked: `tests/test_arp_consumer_contract.py`.
- The MCP server is stdio only, exposes bounded tools, and stops at protocol `2025-11-25` — `executionkit/mcp/`, ADR-012. Checked: `tests/mcp/`.
- Cost uses caller-supplied rates; no price table is bundled — `executionkit/cost.py`, ADR-005. Checked: `tests/test_types.py`.
- Failure-corpus goldens pass 100%; model-judged evals are advisory only — `tests/eval_failure_cases.py`, ADR-006/013. Checked: `tests/test_eval_failure_corpus.py` in the `ci.yml` `test` job. The Claude-in-CI eval is never a required check.

## High-risk areas and what to look for there
| Path | Look for |
|---|---|
| `executionkit/approval.py` | Fail-open or default-approve paths; timeout policy changes; sync callbacks blocking the event loop. |
| `executionkit/provider.py` | URL scheme handling, header or key leakage, unredacted error text, retry/backoff and token-count range checks. |
| `executionkit/claude_sdk.py` | Anything that passes, logs or inherits credentials into the CLI subprocess; silently ignored options. |
| `executionkit/routing.py` | A rule or fallback that sends a prompt to an unintended provider. |
| `executionkit/mcp/**` | Writes to stdout other than JSON-RPC frames; new tools or transports; env-var handling; protocol-version claims without the machinery. |
| `executionkit/evals.py` | Loosened thresholds; live-eval gating that turns a missing secret into a failure or a silent pass. |
| `scripts/claude_ci_eval.py` | Subprocess arguments, model output trusted without schema validation, gating flag semantics. |
| `tests/eval_failure_cases.py` | Edited expectations that make a failing case pass; deleted cases. |
| `.github/**` | Unpinned actions (must be 40-hex SHA with a tag comment), widened `permissions`, secrets exposed to fork PRs, `pull_request_target`, changes to the publish job. |
| `pyproject.toml`, `requirements.lock` | New runtime dependencies; lowered coverage floor; lock drift. |

## Conventions the reviewer should assume
- Flat layout: package at `executionkit/`, not `src/`. Async first, with sync wrappers.
- Python 3.11+, `mypy --strict`, ruff (`check` and `format`), config in `pyproject.toml` only.
- New patterns go through `checked_complete()` / `checked_stream()` so retry, budget and tracing stay uniform.
- Architecture changes get an ADR in `docs/adr/`; user-visible changes get a CHANGELOG entry.

## Do not flag (repo-specific)
- `urllib` in `provider.py`: it is deliberate (zero dependencies); bandit B310 is skipped in config.
- Fake credentials in redaction tests; they are allowlisted in `.gitleaks.toml`.
- `S101`/`S105`/`S106` in tests, and `S603` in the two listed files.
- Missing `opentelemetry`, `jsonschema` or `claude_agent_sdk` imports: they are optional and handled by mypy overrides.

## Severity calibration for this repo
- Blocker: a credential leak, a fail-open approval or security default, a new required runtime dependency, an unpinned or privilege-widened workflow, broken consumer contract.
- High: behavior change in a public pattern without tests or a CHANGELOG entry, weakened validation in `react_loop`, mock-only coverage of a new provider path.
- Medium: missing ADR for an architectural change, docs out of step with code.
- Low or skip: style that ruff and mypy already enforce.

## Out of scope for AI review
- Release, tag and PyPI publish decisions.
- Branch protection and repository settings.
- Documentation prose style, lock hashes, and changelog wording.
