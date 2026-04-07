# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-04-06

### Security

- Fix prompt injection in `refine_loop` default evaluator via XML delimiter sandboxing and input truncation to 32 768 chars (P0-2)
- Mask API key in `Provider.__repr__` — previously leaked `sk-...` values in logs and tracebacks (P2-SEC-06)
- Redact credential-pattern substrings from HTTP error messages using `_redact_sensitive` regex (P2-SEC-07)
- Return only exception type name (not message) from tool error handler in `react_loop` to prevent leaking internal details to the LLM (P2-SEC-08)
- Add Bandit SAST job to CI and Dependabot weekly auto-update configuration for pip and GitHub Actions (P1-14)

### Added

- Add optional `httpx` backend for HTTP connection pooling — install with `pip install executionkit[httpx]`; falls back to `urllib` when `httpx` is absent (P1-5)
- Add `max_history_messages: int | None` parameter to `react_loop` for capping message history size; always preserves the original user prompt (P2-PERF-07)
- Add `_validate_tool_args` helper in `react_loop` that validates tool call arguments against JSON Schema (required fields, `additionalProperties`, and type checks) before execution — uses stdlib only, no `jsonschema` dependency (P1-4)
- Add `aclose()` and async context manager support (`__aenter__`/`__aexit__`) to `Provider` for explicit HTTP client lifecycle management (P1-5)
- Add `messages_trimmed` counter to `react_loop` metadata (P2-PERF-07)

### Fixed

- Fix `consensus` voting incorrectly splitting semantically identical responses that differ only in trailing newlines or internal whitespace — votes now use normalized text while the original winning response is preserved (P2-M2)
- Fix `_parse_score` silently accepting scores outside the 0–10 range; now raises `ValueError` for out-of-range values (P2-M3)
- Remove phantom `pydantic>=2.0` from `project.dependencies`; pydantic was never imported in the library source (P1-15)

### Changed

- Change `PatternResult.metadata` type from `dict[str, Any]` to `MappingProxyType[str, Any]` to enforce true immutability on a frozen dataclass (P2-M6)
