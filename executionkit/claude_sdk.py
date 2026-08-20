"""Claude Agent SDK transport — run ExecutionKit on a Claude subscription.

The rest of ExecutionKit reaches a model one of two ways, and both need an API
key in the environment: :mod:`executionkit.provider` speaks the
OpenAI-compatible ``/chat/completions`` dialect, and :mod:`executionkit.batches`
speaks Anthropic's Message Batches API. This module is a third transport with a
different *auth* story rather than a different dialect: ``claude-agent-sdk``
drives a locally installed Claude Code CLI, which authenticates with the
operator's **Claude subscription sign-in**. No ``ANTHROPIC_API_KEY`` is read,
stored, or forwarded here — credential resolution belongs entirely to the CLI.

Install the optional extra and sign in once::

    pip install 'executionkit[claude]'
    claude          # interactive sign-in, once per machine

Deliberate capability gaps
--------------------------
The Agent SDK is an *agent harness*, not a raw completions endpoint, and
``ClaudeAgentOptions`` exposes no sampling controls. This module does not
emulate the missing ones, because a silently-ignored knob is worse than an
absent one:

* **No ``temperature``.** There is no sampling-temperature parameter anywhere in
  the Agent SDK surface. Passing a non-``None`` ``temperature`` warns. This
  matters most for :func:`executionkit.consensus`, whose sample diversity
  normally comes from temperature — over this transport the samples are only as
  diverse as the model's own nondeterminism, so treat a unanimous vote as weaker
  evidence than the same vote over :class:`~executionkit.provider.Provider`.
* **No ``max_tokens``.** The harness bounds work by turns and spend, not by
  output tokens. Use ``max_budget_usd`` (a hard per-call ceiling) instead; a
  non-``None`` ``max_tokens`` warns.
* **No OpenAI tool schemas.** The Agent SDK executes its own built-in and MCP
  tools rather than returning ``tool_calls`` for the caller to run, which is the
  inverse of what :func:`executionkit.react_loop` needs. This class therefore
  does *not* set ``supports_tools``, so ``react_loop`` rejects it up front with
  its usual message rather than failing halfway through a loop.

**API-key environment variables are scrubbed from the CLI subprocess.** The SDK
spawns the CLI with ``{**os.environ, **options.env}``, so a process that has
``ANTHROPIC_API_KEY`` set -- which any process using
:class:`~executionkit.batches.AnthropicBatchClient` does -- would hand the child
that key, and the CLI authenticates with it. The effect is a silent
credential-class switch: the call bills the API account rather than the
subscription, and fails outright when the key is invalid or unfunded. Verified
directly against the CLI: an invalid inherited key returns
``401 API key is invalid``, and blanking the variable restores the subscription
path. Blanked rather than removed because ``options.env`` merges *over*
``os.environ`` and so can only override, never unset.

What it does map: ``effort`` and ``thinking`` are the harness's own quality
knobs and are exposed as constructor arguments; token usage and the
harness-reported ``total_cost_usd`` flow into
:class:`~executionkit.provider.LLMResponse` and the OTel span; and subscription
rate-limit rejections become :class:`~executionkit.errors.RateLimitError` with a
real ``retry_after``.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal

from executionkit.errors import PermanentError, ProviderError, RateLimitError
from executionkit.observability import llm_span, record_llm_span_attributes
from executionkit.provider import LLMResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

# ---------------------------------------------------------------------------
# claude-agent-sdk availability probe (done once at import time)
# ---------------------------------------------------------------------------

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        CLINotFoundError,
        RateLimitEvent,
        ResultMessage,
        StreamEvent,
        TextBlock,
        query,
    )

    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - import-time state, not a branch
    _SDK_AVAILABLE = False

_INSTALL_HINT: Final[str] = (
    "ClaudeAgentProvider requires the 'claude' extra: "
    "pip install 'executionkit[claude]'"
)

_SIGN_IN_HINT: Final[str] = (
    "The Claude Code CLI was not found. Install it and sign in once "
    "(see https://code.claude.com/docs) — this transport authenticates with "
    "your Claude subscription, not an API key."
)

DEFAULT_MODEL: Final[str] = "claude-opus-5"
"""Model used when the caller does not name one."""

_DEFAULT_RETRY_AFTER: Final[float] = 60.0
"""Fallback retry delay when a rate-limit event carries no reset timestamp."""

_HTTP_CLIENT_ERROR_FLOOR: Final[int] = 400
_HTTP_SERVER_ERROR_FLOOR: Final[int] = 500
_HTTP_TOO_MANY_REQUESTS: Final[int] = 429

# AssistantMessage.error literals that will never succeed on retry.
_PERMANENT_ERRORS: Final[frozenset[str]] = frozenset(
    {"authentication_failed", "billing_error", "invalid_request"}
)

_ROLE_LABELS: Final[dict[str, str]] = {"user": "Human", "assistant": "Assistant"}

#: Credential variables blanked in the CLI subprocess so it cannot fall back to
#: API-key auth. Empty rather than absent: ``ClaudeAgentOptions.env`` is merged
#: over ``os.environ`` and can only override a key, never remove it.
_API_KEY_ENV_VARS: Final[tuple[str, ...]] = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
)


def subscription_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Build the child-process env that pins the CLI to subscription auth.

    Caller *overrides* apply last, so deliberately choosing API-key billing in a
    process that has a key stays possible -- it just has to be said, rather than
    happening by accident because a variable was in the environment.
    """
    env = dict.fromkeys(_API_KEY_ENV_VARS, "")
    if overrides:
        env.update(overrides)
    return env


def _retry_after_from(resets_at: int | None) -> float:
    """Seconds until *resets_at*, floored at 1s, or the default when absent."""
    if resets_at is None:
        return _DEFAULT_RETRY_AFTER
    return max(1.0, float(resets_at) - time.time())


def _split_messages(messages: Sequence[dict[str, Any]]) -> tuple[str | None, str]:
    """Split OpenAI-style *messages* into an Agent SDK ``(system, prompt)`` pair.

    System turns are concatenated into the harness's ``system_prompt``. The
    remaining turns become the prompt: a lone user turn is passed through
    verbatim, while a genuine multi-turn history is rendered as a labelled
    transcript. The Agent SDK's streaming-input mode only accepts *user*
    messages — assistant turns are produced by the model — so replaying a prior
    assistant turn has no lossless representation, and a transcript is the
    honest approximation.
    """
    system_parts: list[str] = []
    turns: list[tuple[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = message.get("content")
        text = "" if content is None else str(content)
        if role == "system":
            system_parts.append(text)
        else:
            turns.append((role, text))

    system = "\n\n".join(part for part in system_parts if part) or None
    if len(turns) == 1:
        return system, turns[0][1]
    transcript = "\n\n".join(
        f"{_ROLE_LABELS.get(role, role.capitalize())}: {text}" for role, text in turns
    )
    return system, transcript


def _warn_unsupported(name: str, alternative: str) -> None:
    """Warn that an ExecutionKit knob has no Agent SDK equivalent."""
    warnings.warn(
        f"ClaudeAgentProvider ignores {name}: the Claude Agent SDK exposes no "
        f"such control. {alternative}",
        UserWarning,
        stacklevel=3,
    )


def _usage_mapping(result: ResultMessage | None) -> MappingProxyType[str, Any]:
    """Project a ``ResultMessage`` into an ``LLMResponse.usage`` mapping.

    ``LLMResponse`` already understands Anthropic's ``input_tokens`` /
    ``output_tokens`` spelling, which is what the harness reports, so those keys
    pass through unchanged.
    """
    if result is None or not result.usage:
        return MappingProxyType({})
    usage = dict(result.usage)
    if result.total_cost_usd is not None:
        usage["total_cost_usd"] = result.total_cost_usd
    return MappingProxyType(usage)


def _text_delta(event: StreamEvent) -> str:
    """Extract the text delta from a raw Anthropic stream event, if any."""
    raw = event.event
    if raw.get("type") != "content_block_delta":
        return ""
    delta = raw.get("delta")
    if not isinstance(delta, dict) or delta.get("type") != "text_delta":
        return ""
    text = delta.get("text")
    return text if isinstance(text, str) else ""


@dataclass(frozen=True, slots=True)
class ClaudeAgentProvider:
    """``LLMProvider`` backed by the Claude Agent SDK and a subscription sign-in.

    Satisfies :class:`~executionkit.provider.LLMProvider` and
    :class:`~executionkit.provider.StreamingProvider` structurally. It
    deliberately does **not** satisfy
    :class:`~executionkit.provider.ToolCallingProvider` — see the module
    docstring for why.

    Args:
        model: Claude model id. Defaults to :data:`DEFAULT_MODEL`.
        system_prompt: Prepended ahead of any ``system`` turn in ``messages``.
        effort: Harness reasoning-depth knob, the closest analogue to the
            sampling controls this transport lacks.
        thinking: Extended-thinking configuration, passed through verbatim.
        max_budget_usd: Hard per-call spend ceiling enforced by the harness.
        cwd: Working directory handed to the CLI.
        max_turns: Turn ceiling. ``1`` keeps the harness to a single completion,
            which is what every non-agentic pattern wants.
        env: Extra environment for the CLI subprocess, applied over the API-key
            scrub. Use it to deliberately restore API-key authentication.
    """

    model: str = DEFAULT_MODEL
    system_prompt: str | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    thinking: dict[str, Any] | None = None
    max_budget_usd: float | None = None
    cwd: str | None = None
    max_turns: int = 1
    env: dict[str, str] = field(default_factory=dict)
    extra_options: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not _SDK_AVAILABLE:
            raise ImportError(_INSTALL_HINT)

    # -- option assembly ---------------------------------------------------

    def _build_options(
        self,
        system: str | None,
        *,
        include_partial_messages: bool = False,
    ) -> ClaudeAgentOptions:
        """Assemble ``ClaudeAgentOptions`` with every tool disabled."""
        merged_system = "\n\n".join(
            part for part in (self.system_prompt, system) if part
        )
        options: dict[str, Any] = {
            "model": self.model,
            # An empty tool set plus an empty allow-list keeps the harness to
            # plain completion: no filesystem, shell, or network side effects.
            "tools": [],
            "allowed_tools": [],
            "max_turns": self.max_turns,
            "permission_mode": "default",
            "include_partial_messages": include_partial_messages,
            # Without this the CLI inherits ANTHROPIC_API_KEY from the parent
            # process and bills the API account instead of the subscription.
            "env": subscription_env(self.env),
            **self.extra_options,
        }
        if merged_system:
            options["system_prompt"] = merged_system
        if self.effort is not None:
            options["effort"] = self.effort
        if self.thinking is not None:
            options["thinking"] = self.thinking
        if self.max_budget_usd is not None:
            options["max_budget_usd"] = self.max_budget_usd
        if self.cwd is not None:
            options["cwd"] = self.cwd
        return ClaudeAgentOptions(**options)

    @staticmethod
    def _check_unsupported(
        temperature: float | None,
        max_tokens: int | None,
        tools: Sequence[dict[str, Any]] | None,
    ) -> None:
        """Warn on knobs with no Agent SDK equivalent; reject tool schemas."""
        if temperature is not None:
            _warn_unsupported(
                "temperature",
                "Use the 'effort' constructor argument to trade depth for cost.",
            )
        if max_tokens is not None:
            _warn_unsupported(
                "max_tokens",
                "Use the 'max_budget_usd' constructor argument to cap a call.",
            )
        if tools:
            raise PermanentError(
                "ClaudeAgentProvider cannot accept OpenAI tool schemas: the "
                "Claude Agent SDK executes its own tools rather than returning "
                "tool calls for the caller to run. Use Provider for "
                "react_loop(), or configure MCP servers on the harness."
            )

    # -- message-stream handling -------------------------------------------

    @staticmethod
    def _raise_for_rate_limit(event: RateLimitEvent) -> None:
        """Translate a rejected subscription rate-limit event into an error."""
        info = event.rate_limit_info
        if info.status != "rejected":
            return
        raise RateLimitError(
            f"Claude subscription rate limit reached "
            f"({info.rate_limit_type or 'unknown window'}).",
            retry_after=_retry_after_from(info.resets_at),
        )

    @staticmethod
    def _raise_for_assistant_error(message: AssistantMessage) -> None:
        """Translate an ``AssistantMessage.error`` into the EK error tree."""
        error = message.error
        if error is None:
            return
        detail = f"Claude Agent SDK reported '{error}'."
        if error == "rate_limit":
            raise RateLimitError(detail, retry_after=_DEFAULT_RETRY_AFTER)
        if error in _PERMANENT_ERRORS:
            raise PermanentError(detail)
        raise ProviderError(detail)

    @staticmethod
    def _raise_for_result(result: ResultMessage) -> None:
        """Translate a failed ``ResultMessage`` into the EK error tree."""
        if not result.is_error:
            return
        detail = "; ".join(result.errors or []) or result.subtype
        status = result.api_error_status
        message = f"Claude Agent SDK run failed: {detail}"
        if status == _HTTP_TOO_MANY_REQUESTS:
            raise RateLimitError(message, retry_after=_DEFAULT_RETRY_AFTER)
        if status is not None and (
            _HTTP_CLIENT_ERROR_FLOOR <= status < _HTTP_SERVER_ERROR_FLOOR
        ):
            raise PermanentError(message)
        raise ProviderError(message)

    def _consume_common(self, message: object) -> ResultMessage | None:
        """Apply the error checks shared by ``complete`` and ``stream``.

        Returns the ``ResultMessage`` when *message* is one, else ``None``.
        """
        if isinstance(message, RateLimitEvent):
            self._raise_for_rate_limit(message)
        elif isinstance(message, AssistantMessage):
            self._raise_for_assistant_error(message)
        elif isinstance(message, ResultMessage):
            self._raise_for_result(message)
            return message
        return None

    # -- LLMProvider -------------------------------------------------------

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Run one harness turn and return the assistant text as an LLMResponse."""
        self._check_unsupported(temperature, max_tokens, tools)
        system, prompt = _split_messages(messages)
        options = self._build_options(system)

        chunks: list[str] = []
        result: ResultMessage | None = None
        with llm_span(self.model) as span:
            try:
                async for message in query(prompt=prompt, options=options):
                    result = self._consume_common(message) or result
                    if isinstance(message, AssistantMessage):
                        chunks.extend(
                            block.text
                            for block in message.content
                            if isinstance(block, TextBlock)
                        )
            except CLINotFoundError as exc:
                raise PermanentError(_SIGN_IN_HINT) from exc

            response = LLMResponse(
                content="".join(chunks),
                finish_reason=(result.stop_reason if result else None) or "stop",
                usage=_usage_mapping(result),
                raw=result,
            )
            record_llm_span_attributes(
                span,
                self.model,
                response.input_tokens,
                response.output_tokens,
                result.total_cost_usd if result else None,
            )
        return response

    # -- StreamingProvider -------------------------------------------------

    def stream(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: Sequence[dict[str, Any]] | None = None,
        usage_sink: list[LLMResponse] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Return an async iterator over text deltas (call without ``await``)."""
        self._check_unsupported(temperature, max_tokens, tools)
        return self._stream(messages, usage_sink)

    async def _stream(
        self,
        messages: Sequence[dict[str, Any]],
        usage_sink: list[LLMResponse] | None,
    ) -> AsyncIterator[str]:
        """Drive the harness with partial messages on, yielding text deltas."""
        system, prompt = _split_messages(messages)
        options = self._build_options(system, include_partial_messages=True)

        chunks: list[str] = []
        result: ResultMessage | None = None
        try:
            async for message in query(prompt=prompt, options=options):
                result = self._consume_common(message) or result
                if isinstance(message, StreamEvent):
                    delta = _text_delta(message)
                    if delta:
                        chunks.append(delta)
                        yield delta
        except CLINotFoundError as exc:
            raise PermanentError(_SIGN_IN_HINT) from exc

        if usage_sink is not None:
            usage_sink.append(
                LLMResponse(
                    content="".join(chunks),
                    finish_reason=(result.stop_reason if result else None) or "stop",
                    usage=_usage_mapping(result),
                    raw=result,
                )
            )
