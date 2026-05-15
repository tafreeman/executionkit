# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Add the `structured()` pattern and `structured_sync()` wrapper for JSON extraction, optional validation, and repair retries.
- Add MkDocs Material documentation with public guides for installation, provider setup, patterns, recipes, API reference, contributing, license, and changelog.
- Add architecture decision records for structural protocols, flat package layout, and the single OpenAI-compatible provider design.
- Add a GitHub Pages documentation deployment workflow and CodeQL analysis workflow.
- Add supply-chain artifacts and release hardening, including `requirements.lock`, `sbom.json`, and SBOM artifact generation in the publish workflow.
- Add C4 diagram source files for ExecutionKit component and relationship documentation.

### Changed

- Update GitHub Actions workflow dependencies to current major versions for checkout, setup-python, upload/download artifacts, Pages upload/deploy, and CodeQL.
- Replace the old Astro documentation site with the MkDocs Material site.
- Clarify the relationship between ExecutionKit and the companion `agentic-runtimes` orchestration repo in the README and docs.
- Exclude internal planning, review, C4, superpowers, and test-audit documents from the public MkDocs build while keeping them in the repository.

### Fixed

- Fix strict MkDocs builds by excluding internal documents with stale cross-references from the public site.
- Remove obsolete Serena project files from the tracked repo state.
- Clean up async test markers now covered by the project-level pytest asyncio configuration.

## [0.1.0] - 2026-04-06

### Security

- Fix prompt injection in `refine_loop` default evaluator via XML delimiter sandboxing and input truncation to 32 768 chars
- Mask API key in `Provider.__repr__` — previously leaked `sk-...` values in logs and tracebacks
- Redact credential-pattern substrings from HTTP error messages using `_redact_sensitive` regex
- Return only exception type name (not message) from tool error handler in `react_loop` to prevent leaking internal details to the LLM
- Add Bandit SAST job to CI and Dependabot weekly auto-update configuration for pip and GitHub Actions

### Added

- Add optional `httpx` backend for HTTP connection pooling — install with `pip install executionkit[httpx]`; falls back to `urllib` when `httpx` is absent
- Add `max_history_messages: int | None` parameter to `react_loop` for capping message history size; always preserves the original user prompt
- Add `_validate_tool_args` helper in `react_loop` that validates tool call arguments against JSON Schema (required fields, `additionalProperties`, and type checks) before execution — uses stdlib only, no `jsonschema` dependency
- Add `aclose()` and async context manager support (`__aenter__`/`__aexit__`) to `Provider` for explicit HTTP client lifecycle management
- Add `messages_trimmed` counter to `react_loop` metadata

### Fixed

- Fix `consensus` voting incorrectly splitting semantically identical responses that differ only in trailing newlines or internal whitespace — votes now use normalized text while the original winning response is preserved
- Fix `_parse_score` silently accepting scores outside the 0–10 range; now raises `ValueError` for out-of-range values
- Remove phantom `pydantic>=2.0` from `project.dependencies`; pydantic was never imported in the library source

### Changed

- Change `PatternResult.metadata` type from `dict[str, Any]` to `MappingProxyType[str, Any]` to enforce true immutability on a frozen dataclass
