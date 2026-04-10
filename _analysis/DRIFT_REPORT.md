# Drift Report

- [x] `.claude/settings.local.json` allowlist referenced `src/executionkit/...` and machine-specific paths. Updated to the `executionkit/` root commands and trimmed to repo-relevant lint/type/test workflows.
- [x] `README.md` claimed ~300 tests; pytest currently collects 340 tests (coverage ~83%). Updated the Development section to reflect the current counts.
- [x] `BUILD_SPEC.md` still referenced `src/executionkit/`, `pydantic`, and outdated docs-site wording. Marked it historical and aligned the major drift points with the current repo layout/runtime dependency story.
- [x] `SECURITY.md`, `BACKLOG.md`, `ROADMAP_V2.md`, and `evaluation_result.md` contained stale statements about already-shipped work. Added historical/status notes and corrected the prompt-injection guidance.
