# Full Review Playbooks

This directory holds human-readable playbooks for deep review passes. They are not auto-loaded by any tool; open the files directly when running a quality, security, performance, or documentation review.

## Layout
- `00-scope.md` through `05-final-report.md` — end-to-end review flow from scoping to final reporting.
- `1a-*.md`, `2a-*.md`, `3a-*.md`, `4a-*.md`, `4b-cicd.md` — focused checklists for specific dimensions (code quality, architecture, security, performance, testing, documentation, CI/CD).
- `code-quality-review.md`, `SECURITY_AUDIT.md` — ready-to-use templates for common review types.
- `state.json` — scratchpad used by some reviewers to track progress; do not rely on it as canonical state.

## Usage
- Start with `00-scope.md` to plan the review, then apply the dimension-specific checklists as needed.
- Keep guidance here consistent with repo-wide conventions in `AGENTS.md`, `CONTRIBUTING.md`, and `docs/architecture.md`. Cross-link rather than duplicating rules.
- Record any discrepancies between these playbooks and live workflows in `_analysis/DRIFT_REPORT.md`.
