# Agents Guide

This repository includes several agent-specific configuration directories. Use this guide to understand which rules are canonical and where to find them.

## Assets and Canonical Roles
- `.claude/` — Anthropic/Claude desktop settings file. Source of truth for the command allowlist that Claude loads automatically. See `.claude/README.md` for layout and update steps.
- `.serena/` — Serena project configuration for language servers and editor behaviour. See `.serena/README.md`.
- `.full-review/` — Human-readable playbooks and templates for deep review passes (quality, security, performance, documentation). See `.full-review/README.md`.

## Repo-Wide Conventions for All Agents
- Python 3.11+; install with `pip install -e ".[dev]"`.
- Standard checks: `ruff check .`, `ruff format . --check`, `mypy --strict executionkit/`, `pytest --cov=executionkit --cov-fail-under=80`.
- Primary docs: `README.md` (product + usage), `docs/architecture.md` (module map + invariants), `CONTRIBUTING.md` (workflow), `SECURITY.md` (reporting + rules).
- Credentials: never commit secrets; examples must read keys from environment variables.

## Coordination and Drift
- Known stale allowlist entries (e.g., `src/executionkit` paths) are recorded in `_analysis/DRIFT_REPORT.md`. Update the machine-loaded config alongside this guide when layout or workflows change.
- Add new agent rules to the directory that loads them, then cross-link from here instead of duplicating text.
