# Claude Configuration

`settings.local.json` defines the allowlisted commands Claude Desktop loads automatically when this repo is active. It focuses on the standard lint/type/test workflows for the `executionkit/` package plus a handful of targeted test invocations.

## Layout
- `settings.local.json` — Command allowlist covering linting (`ruff`), type checks (`mypy`), full and targeted pytest runs, and basic repo inspection commands.

## Maintenance
- The code lives in `executionkit/` at the repo root (no `src/` prefix). The allowlist has been trimmed to repo-specific commands; avoid adding machine-specific paths or unrelated directories.
- Keep the allowlist aligned with the canonical workflows in `CONTRIBUTING.md` and `AGENTS.md`. Track any needed exceptions or drift in `_analysis/DRIFT_REPORT.md` rather than embedding policy here.
- Do not add secrets or environment-specific keys; prefer environment variables for credentials.
