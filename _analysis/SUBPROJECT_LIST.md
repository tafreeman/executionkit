# Subproject List

Discovery date: 2026-04-08

Detection method: searched for build manifests (pyproject.toml, package.json, go.mod, Cargo.toml) and language-specific entry points; reviewed top-level folders for independent stacks or test suites.

## Included
- **executionkit** (Python package) — Root `pyproject.toml`, shared dev dependencies, and a single pytest suite under `tests/` confirm one cohesive library.

## Excluded
- **docs/** — Documentation assets only; no build tooling or executable modules.
- **examples/** — Usage samples that rely on the main package; not packaged separately.
- **planning/** — Planning and review notes; not runnable code.
- **.full-review/** — Guidance and templates for audits; referenced as agent config, not a built artifact.
