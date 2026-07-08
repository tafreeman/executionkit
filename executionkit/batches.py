"""Anthropic Message Batches fan-out for consensus / map-reduce workloads.

The live patterns (:mod:`executionkit.patterns`) fan out with ``asyncio``
concurrency against an OpenAI-compatible endpoint. This module is a second,
deliberately separate transport: Anthropic's native **Message Batches API**
(``POST /v1/messages/batches``), which trades latency for throughput and
cost — a batch is submitted once, processed asynchronously by the provider,
and collected when it ends. Suited to large consensus fan-outs and offline
map-reduce jobs where nobody is waiting on a socket.

Design (see docs/adr/014-message-batches.md for the full rationale):

* **Zero-dependency.** HTTP is stdlib ``urllib`` run in a worker thread —
  the same transport choice as :class:`executionkit.provider.Provider`'s
  default path, with the same redirect hygiene: the ``x-api-key`` credential
  is attached as an *unredirected* header so it is never resent to a
  cross-host redirect target.
* **Anthropic-native, not OpenAI-compatible.** The rest of ExecutionKit
  speaks the OpenAI ``/chat/completions`` dialect; batching has no equivalent
  inline-JSON surface there, so this module pins Anthropic's endpoint and
  ``anthropic-version`` header instead of pretending the two dialects unify.
* **Same voting semantics as the live pattern.**
  :func:`consensus_batch` scores samples with the identical
  :func:`executionkit.engine.voting.tally_votes` used by
  :func:`executionkit.consensus` — one voting implementation, two transports.
* **Strict failure semantics.** Any errored/canceled/expired entry in the
  batch raises :class:`~executionkit.errors.ProviderError` naming the failed
  ``custom_id``s, mirroring ``gather_strict``'s all-or-nothing behaviour in
  the live fan-out. Partial results are never silently returned.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from executionkit._constants import DEFAULT_MAX_TOKENS
from executionkit.engine.messages import user_message
from executionkit.engine.voting import tally_votes
from executionkit.errors import LLMError, ProviderError, RateLimitError
from executionkit.types import PatternResult, TokenUsage, VotingStrategy

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

DEFAULT_ANTHROPIC_BASE_URL: Final[str] = "https://api.anthropic.com"
"""Base URL for the Anthropic API; overridable for proxies and tests."""

ANTHROPIC_VERSION: Final[str] = "2023-06-01"
"""Pinned ``anthropic-version`` header (the Batches API's stable version)."""

DEFAULT_HTTP_TIMEOUT_SECONDS: Final[float] = 60.0
"""Per-HTTP-request timeout; distinct from the batch-completion timeout."""

DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 5.0
"""Delay between ``processing_status`` polls while a batch is in flight."""

DEFAULT_BATCH_TIMEOUT_SECONDS: Final[float] = 1800.0
"""Default wall-clock budget for a batch to end (Anthropic allows up to 24h;
callers running true offline jobs should raise this explicitly)."""

DEFAULT_BATCH_TEMPERATURE: Final[float] = 0.9
"""Default sampling temperature for consensus_batch — matches the live
consensus pattern's high-diversity default."""

_BATCH_ENDED_STATUS: Final[str] = "ended"
_RESULT_SUCCEEDED: Final[str] = "succeeded"
_ERROR_BODY_PREVIEW_CHARS: Final[int] = 500


def _map_http_error(status: int, body_preview: str, retry_after: float) -> LLMError:
    """Map an HTTP error status from the Batches API to the EK error hierarchy.

    Pure so tests can exercise the mapping without a network or a fake server:
    429 becomes a retryable :class:`RateLimitError`; everything else surfaces
    as :class:`ProviderError` with a truncated body preview for diagnosis.
    """
    if status == 429:
        return RateLimitError(
            f"Batches API rate-limited (HTTP 429): {body_preview}",
            retry_after=retry_after,
        )
    return ProviderError(f"Batches API request failed (HTTP {status}): {body_preview}")


@dataclass(frozen=True, slots=True)
class _BatchEntry:
    """One parsed line of a batch results file."""

    custom_id: str
    succeeded: bool
    text: str
    input_tokens: int
    output_tokens: int
    failure_type: str


class AnthropicBatchClient:
    """Minimal stdlib client for the Anthropic Message Batches API.

    Exposes exactly the three calls the fan-out helpers need: create a batch,
    poll it, and fetch its results file. All transport goes through
    :meth:`_http_raw` — the single seam tests replace to run without a
    network.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_ANTHROPIC_BASE_URL,
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must be a non-empty string")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError(f"base_url must be http(s), got {base_url!r}")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def create_batch(
        self, requests: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """``POST /v1/messages/batches`` with the given request entries."""
        if not requests:
            raise ValueError("cannot create a batch with no requests")
        payload = json.dumps({"requests": list(requests)}).encode("utf-8")
        raw = await asyncio.to_thread(
            self._http_raw, "POST", f"{self.base_url}/v1/messages/batches", payload
        )
        return self._decode_json_object(raw, context="create_batch")

    async def get_batch(self, batch_id: str) -> dict[str, Any]:
        """``GET /v1/messages/batches/{id}`` — the polling call."""
        url = f"{self.base_url}/v1/messages/batches/{batch_id}"
        raw = await asyncio.to_thread(self._http_raw, "GET", url, None)
        return self._decode_json_object(raw, context="get_batch")

    async def fetch_results(self, results_url: str) -> list[dict[str, Any]]:
        """Fetch and parse the JSONL results file of an ended batch."""
        if not results_url.startswith(("https://", "http://")):
            raise ProviderError(
                f"batch results_url has unexpected scheme: {results_url!r}"
            )
        raw = await asyncio.to_thread(self._http_raw, "GET", results_url, None)
        entries: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    f"batch results line {line_number} is not valid JSON: {exc}"
                ) from exc
            if not isinstance(parsed, dict):
                raise ProviderError(
                    f"batch results line {line_number} is not a JSON object"
                )
            entries.append(parsed)
        return entries

    @staticmethod
    def _decode_json_object(raw: bytes, *, context: str) -> dict[str, Any]:
        """Decode *raw* as a JSON object, raising ProviderError otherwise."""
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"{context}: response is not valid JSON: {exc}"
            ) from exc
        if not isinstance(decoded, dict):
            raise ProviderError(f"{context}: response is not a JSON object")
        return decoded

    def _http_raw(self, method: str, url: str, body: bytes | None) -> bytes:
        """Blocking HTTP round-trip — the single transport seam (tests stub this).

        Mirrors ``Provider._post_urllib``'s hygiene: the ``x-api-key``
        credential is attached unredirected so it cannot leak to a cross-host
        redirect target, and error statuses map through :func:`_map_http_error`.
        """
        req = urllib.request.Request(url, data=body, method=method)  # noqa: S310
        req.add_unredirected_header("x-api-key", self.api_key)
        req.add_header("anthropic-version", ANTHROPIC_VERSION)
        if body is not None:
            req.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                data: bytes = resp.read()
                return data
        except urllib.error.HTTPError as exc:
            body_preview = exc.read().decode("utf-8", "replace")[
                :_ERROR_BODY_PREVIEW_CHARS
            ]
            retry_after_header = (
                exc.headers.get("retry-after", "1") if exc.headers else "1"
            )
            try:
                retry_after = float(retry_after_header)
            except ValueError:
                retry_after = 1.0
            raise _map_http_error(exc.code, body_preview, retry_after) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"Batches API transport failure: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ProviderError(f"Batches API request timed out: {exc}") from exc


async def _await_batch_end(
    client: AnthropicBatchClient,
    batch_id: str,
    *,
    poll_interval: float,
    timeout: float,
) -> dict[str, Any]:
    """Poll *batch_id* until ``processing_status == "ended"`` or *timeout*."""
    deadline = time.monotonic() + timeout
    while True:
        batch = await client.get_batch(batch_id)
        if batch.get("processing_status") == _BATCH_ENDED_STATUS:
            return batch
        if time.monotonic() >= deadline:
            raise ProviderError(
                f"batch {batch_id} did not end within {timeout}s "
                f"(last status: {batch.get('processing_status')!r})"
            )
        await asyncio.sleep(poll_interval)


def _parse_result_entry(entry: Mapping[str, Any]) -> _BatchEntry:
    """Project one results-file line into a :class:`_BatchEntry`."""
    custom_id = str(entry.get("custom_id", ""))
    result = entry.get("result")
    if not isinstance(result, dict):
        return _BatchEntry(
            custom_id=custom_id,
            succeeded=False,
            text="",
            input_tokens=0,
            output_tokens=0,
            failure_type="malformed_result",
        )
    result_type = str(result.get("type", ""))
    if result_type != _RESULT_SUCCEEDED:
        return _BatchEntry(
            custom_id=custom_id,
            succeeded=False,
            text="",
            input_tokens=0,
            output_tokens=0,
            failure_type=result_type or "unknown",
        )

    message = result.get("message")
    if not isinstance(message, dict):
        return _BatchEntry(
            custom_id=custom_id,
            succeeded=False,
            text="",
            input_tokens=0,
            output_tokens=0,
            failure_type="malformed_message",
        )

    content = message.get("content")
    text_parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))

    usage = message.get("usage")
    input_tokens = 0
    output_tokens = 0
    if isinstance(usage, dict):
        raw_input = usage.get("input_tokens", 0)
        raw_output = usage.get("output_tokens", 0)
        if isinstance(raw_input, int) and not isinstance(raw_input, bool):
            input_tokens = max(0, raw_input)
        if isinstance(raw_output, int) and not isinstance(raw_output, bool):
            output_tokens = max(0, raw_output)

    return _BatchEntry(
        custom_id=custom_id,
        succeeded=True,
        text="".join(text_parts),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        failure_type="",
    )


async def _run_batch(
    client: AnthropicBatchClient,
    requests: Sequence[Mapping[str, Any]],
    *,
    poll_interval: float,
    timeout: float,
) -> tuple[str, dict[str, _BatchEntry], TokenUsage]:
    """Submit *requests*, await the end, and return parsed entries by custom_id.

    Raises ProviderError when the ended batch is missing a ``results_url`` or
    when any entry did not succeed (strict all-or-nothing, like the live
    fan-out's ``gather_strict``).
    """
    created = await client.create_batch(requests)
    batch_id = str(created.get("id", ""))
    if not batch_id:
        raise ProviderError("create_batch response is missing a batch 'id'")

    ended = await _await_batch_end(
        client, batch_id, poll_interval=poll_interval, timeout=timeout
    )
    results_url = ended.get("results_url")
    if not isinstance(results_url, str) or not results_url:
        raise ProviderError(f"batch {batch_id} ended without a results_url")

    raw_entries = await client.fetch_results(results_url)
    entries = {
        parsed.custom_id: parsed
        for parsed in (_parse_result_entry(raw) for raw in raw_entries)
    }

    failed = sorted(
        f"{entry.custom_id} ({entry.failure_type})"
        for entry in entries.values()
        if not entry.succeeded
    )
    if failed:
        raise ProviderError(
            f"batch {batch_id} has {len(failed)} non-succeeded entries: "
            + ", ".join(failed)
        )

    usage = TokenUsage(
        input_tokens=sum(entry.input_tokens for entry in entries.values()),
        output_tokens=sum(entry.output_tokens for entry in entries.values()),
        llm_calls=len(entries),
    )
    return batch_id, entries, usage


def _entry_or_missing(
    entries: Mapping[str, _BatchEntry], custom_id: str, batch_id: str
) -> _BatchEntry:
    """Look up *custom_id*, raising ProviderError if the results omitted it."""
    entry = entries.get(custom_id)
    if entry is None:
        raise ProviderError(f"batch {batch_id} results are missing {custom_id!r}")
    return entry


async def consensus_batch(
    client: AnthropicBatchClient,
    model: str,
    prompt: str,
    *,
    num_samples: int = 5,
    strategy: VotingStrategy | str = "majority",
    temperature: float = DEFAULT_BATCH_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout: float = DEFAULT_BATCH_TIMEOUT_SECONDS,
) -> PatternResult[str]:
    """Consensus over ``num_samples`` identical prompts via one message batch.

    The batch-transport twin of :func:`executionkit.consensus`: same prompt
    replication, same voting (:func:`executionkit.engine.voting.tally_votes`),
    same result shape — but the samples travel as a single Message Batches
    submission instead of ``num_samples`` concurrent live calls.

    Anthropic-Batches-specific: unlike the provider-agnostic headline patterns
    (:func:`executionkit.consensus`, :func:`executionkit.map_reduce`, and
    friends — all of which accept any ``LLMProvider``-conforming object), this
    function only talks to Anthropic's Message Batches API and requires an
    :class:`AnthropicBatchClient` and Anthropic API key — it is not usable
    with an arbitrary OpenAI-compatible endpoint.

    Returns:
        A :class:`PatternResult` whose ``value`` is the winning response and
        ``score`` the agreement ratio.

    Raises:
        ConsensusFailedError: When ``strategy="unanimous"`` and responses
            are not all identical.
        ProviderError: On transport failure, poll timeout, or any
            non-succeeded batch entry.
        ValueError: If ``num_samples`` is less than 1.

    Metadata:
        agreement_ratio (float): Fraction of samples matching the winner.
        unique_responses (int): Number of distinct response strings observed.
        tie_count (int): Number of responses tied for the top vote count.
        batch_id (str): The provider-assigned Message Batches id.
    """
    if num_samples < 1:
        raise ValueError(f"num_samples must be >= 1, got {num_samples}")
    if isinstance(strategy, str):
        strategy = VotingStrategy(strategy)

    requests = [
        {
            "custom_id": f"consensus-{index}",
            "params": {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [user_message(prompt)],
            },
        }
        for index in range(num_samples)
    ]

    batch_id, entries, usage = await _run_batch(
        client, requests, poll_interval=poll_interval, timeout=timeout
    )
    contents = [
        _entry_or_missing(entries, f"consensus-{index}", batch_id).text
        for index in range(num_samples)
    ]
    tally = tally_votes(contents, strategy)

    return PatternResult[str](
        value=tally.winner,
        score=tally.agreement_ratio,
        cost=usage,
        metadata=MappingProxyType(
            {
                "agreement_ratio": tally.agreement_ratio,
                "unique_responses": tally.unique_responses,
                "tie_count": tally.tie_count,
                "batch_id": batch_id,
            }
        ),
    )


async def map_batch(
    client: AnthropicBatchClient,
    model: str,
    prompts: Sequence[str],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float | None = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout: float = DEFAULT_BATCH_TIMEOUT_SECONDS,
) -> PatternResult[tuple[str, ...]]:
    """Map every prompt to a completion via one message batch (fan-out only).

    The "map" half of a map-reduce: one request per prompt, submitted as a
    single batch, with responses returned in prompt order regardless of the
    order the provider finished them. Callers reduce however they like —
    including with :func:`executionkit.engine.voting.tally_votes` for a
    consensus-style reduce over non-identical prompts.

    Anthropic-Batches-specific: like :func:`consensus_batch`, this function
    only talks to Anthropic's Message Batches API — unlike the
    provider-agnostic headline patterns (:func:`executionkit.map_reduce` and
    friends), it is not usable with other OpenAI-compatible endpoints.

    Returns:
        A :class:`PatternResult` whose ``value`` is a tuple of responses,
        index-aligned with ``prompts``. ``score`` is ``None`` (no intrinsic
        quality measure for a map).

    Raises:
        ProviderError: On transport failure, poll timeout, or any
            non-succeeded batch entry (strict all-or-nothing).
        ValueError: If ``prompts`` is empty.

    Metadata:
        batch_id (str): The provider-assigned Message Batches id.
        num_requests (int): Number of prompts submitted.
    """
    if not prompts:
        raise ValueError("prompts must be non-empty")

    requests = []
    for index, prompt in enumerate(prompts):
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [user_message(prompt)],
        }
        if temperature is not None:
            params["temperature"] = temperature
        requests.append({"custom_id": f"map-{index}", "params": params})

    batch_id, entries, usage = await _run_batch(
        client, requests, poll_interval=poll_interval, timeout=timeout
    )
    values = tuple(
        _entry_or_missing(entries, f"map-{index}", batch_id).text
        for index in range(len(prompts))
    )

    return PatternResult[tuple[str, ...]](
        value=values,
        score=None,
        cost=usage,
        metadata=MappingProxyType({"batch_id": batch_id, "num_requests": len(prompts)}),
    )
