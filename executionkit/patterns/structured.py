"""Structured-output pattern: JSON extraction with optional repair/validation."""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from executionkit.cost import CostTracker
from executionkit.engine.json_extraction import extract_json
from executionkit.engine.messages import user_message
from executionkit.engine.retry import RetryConfig  # noqa: TC001
from executionkit.patterns.base import checked_complete
from executionkit.provider import LLMProvider  # noqa: TC001
from executionkit.types import PatternResult, TokenUsage

StructuredValue = dict[str, Any] | list[Any]
StructuredValidator = Callable[[StructuredValue], str | None | bool]
"""Return ``None``, ``True``, or ``""`` to accept a value; otherwise return
``False`` or an error string to trigger repair."""


def _json_prompt(prompt: str) -> str:
    return (
        "Return a valid JSON object or array only. "
        "Do not include markdown fences or extra commentary.\n\n"
        f"{prompt}"
    )


def _normalize_validation_error(result: str | None | bool) -> str | None:
    if result in (None, "", True):
        return None
    if result is False:
        return "Validator rejected the structured output."
    return str(result)


async def structured(
    provider: LLMProvider,
    prompt: str,
    *,
    validator: StructuredValidator | None = None,
    max_retries: int = 3,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    max_cost: TokenUsage | None = None,
    retry: RetryConfig | None = None,
) -> PatternResult[StructuredValue]:
    """Request JSON output, parse it, and optionally repair invalid responses.

    Validators should return ``None``, ``True``, or ``""`` for success. Any
    other value is treated as a validation failure and included in the repair
    prompt. ``max_retries=0`` is supported and means "make one parse attempt
    with no repair call".
    """
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    if max_tokens < 1:
        raise ValueError(f"max_tokens must be >= 1, got {max_tokens}")

    tracker = CostTracker()
    metadata: dict[str, Any] = {
        "parse_attempts": 0,
        "repair_attempts": 0,
        "validated": validator is None,
    }

    response = await checked_complete(
        provider,
        [user_message(_json_prompt(prompt))],
        tracker,
        max_cost,
        retry,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    latest_text = response.content
    last_error = "Structured output could not be produced."

    for attempt in range(max_retries + 1):
        metadata["parse_attempts"] = attempt + 1
        try:
            value = extract_json(latest_text)
        except ValueError as exc:
            last_error = f"JSON parse failed: {exc}"
        else:
            validation_error = (
                None
                if validator is None
                else _normalize_validation_error(validator(value))
            )
            if validation_error is None:
                metadata["validated"] = True
                return PatternResult(
                    value=value,
                    cost=tracker.to_usage(),
                    metadata=MappingProxyType(dict(metadata)),
                )
            last_error = validation_error

        if attempt == max_retries:
            break

        metadata["repair_attempts"] += 1
        repair_prompt = (
            "The previous response was not valid structured output.\n"
            f"Error: {last_error}\n\n"
            "Original task:\n"
            f"{prompt}\n\n"
            "Previous response:\n"
            f"{latest_text}\n\n"
            "Return a corrected JSON object or array only."
        )
        repair_response = await checked_complete(
            provider,
            [user_message(repair_prompt)],
            tracker,
            max_cost,
            retry,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        latest_text = repair_response.content

    raise ValueError(last_error)
