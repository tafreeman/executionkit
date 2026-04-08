# Claude Configuration

`settings.local.json` defines the allowlisted commands loaded by Claude Desktop for this repository. Claude uses this file automatically when the repo is active.

## Layout
- `settings.local.json` — Command allowlist covering linting (`ruff`), type checks (`mypy`), tests (`pytest`), and a few maintenance commands inherited from earlier layouts.

## Maintenance
- The code lives in `executionkit/` at the repo root (no `src/` prefix). Update any stale `src/executionkit/...` paths in the allowlist when adjusting commands. Open drift items are tracked in `_analysis/DRIFT_REPORT.md`.
- Keep the allowlist aligned with the canonical workflows in `CONTRIBUTING.md` and `AGENTS.md`. Avoid duplicating prose here; link to those docs for policy.
- Do not add secrets or environment-specific keys; prefer environment variables for credentials.
