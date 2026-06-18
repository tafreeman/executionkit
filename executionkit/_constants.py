"""Shared default constants for ExecutionKit patterns and engine utilities.

Centralizes values previously duplicated across modules so defaults stay
consistent. Pattern-specific tuning (e.g. per-pattern temperature) stays local
to each module.
"""

DEFAULT_MAX_TOKENS: int = 4096
"""Default ``max_tokens`` for a single LLM completion across patterns."""

DEFAULT_MAX_CONCURRENCY: int = 10
"""Default concurrency cap for fan-out engine utilities and patterns."""

DEFAULT_TOOL_TIMEOUT_SECONDS: float = 30.0
"""Default per-tool execution timeout in seconds."""
