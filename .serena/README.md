# Serena Configuration

`project.yml` configures the Serena assistant for this repository.

## Layout
- `project.yml` — Sets `project_name`, enables the Python language server, applies UTF-8 encoding, and respects `.gitignore` entries.

## Maintenance
- Update `languages` if new stacks are added, and keep `ignored_paths` in sync with repo conventions.
- Keep this config aligned with `AGENTS.md` and `CONTRIBUTING.md`; add links there instead of duplicating rules.
- Do not commit secrets or machine-specific paths; rely on environment variables for credentials.
