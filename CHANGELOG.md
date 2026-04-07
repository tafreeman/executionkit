# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
