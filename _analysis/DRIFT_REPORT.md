# Drift Report

- [ ] `.claude/settings.local.json` allowlist references `src/executionkit/...` paths and commands to move that directory, but the code now lives in `executionkit/` at the repo root. Allowed commands will fail or mislead agents until the allowlist is updated.
- [x] `README.md` claimed ~300 tests; pytest currently collects 340 tests (coverage ~83%). Updated the Development section to reflect the current counts.
