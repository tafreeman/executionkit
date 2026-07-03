"""Tests for the Anthropic Message Batches fan-out (executionkit/batches.py).

All transport goes through ``AnthropicBatchClient._http_raw`` — the single
seam these tests replace with an in-memory fake, so no test ever opens a
socket. HTTP error *mapping* is covered separately via the pure
``_map_http_error`` function.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from executionkit.batches import (
    AnthropicBatchClient,
    _map_http_error,
    consensus_batch,
    map_batch,
)
from executionkit.provider import ConsensusFailedError, ProviderError, RateLimitError

_BATCHES_PATH = "/v1/messages/batches"
_RESULTS_URL = "https://api.anthropic.com/v1/messages/batches/b1/results"


def _succeeded_line(custom_id: str, text: str, *, inp: int = 10, out: int = 5) -> dict:
    return {
        "custom_id": custom_id,
        "result": {
            "type": "succeeded",
            "message": {
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": inp, "output_tokens": out},
            },
        },
    }


def _errored_line(custom_id: str) -> dict:
    return {
        "custom_id": custom_id,
        "result": {"type": "errored", "error": {"type": "invalid_request"}},
    }


class FakeTransport:
    """Routes _http_raw calls: create -> batch, poll -> statuses, results -> JSONL.

    ``poll_statuses`` is consumed one per get_batch call; the last value
    repeats if polled again.
    """

    def __init__(
        self,
        result_lines: list[dict],
        *,
        poll_statuses: list[str] | None = None,
        results_url: str | None = _RESULTS_URL,
    ) -> None:
        self.result_lines = result_lines
        self.poll_statuses = poll_statuses or ["ended"]
        self.results_url = results_url
        self.created_payload: dict | None = None
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, url: str, body: bytes | None) -> bytes:
        self.calls.append((method, url))
        if method == "POST" and url.endswith(_BATCHES_PATH):
            assert body is not None
            self.created_payload = json.loads(body)
            return json.dumps({"id": "b1", "processing_status": "in_progress"}).encode()
        if method == "GET" and url == self.results_url:
            lines = "\n".join(json.dumps(line) for line in self.result_lines)
            return lines.encode()
        if method == "GET" and _BATCHES_PATH in url:
            status = (
                self.poll_statuses.pop(0)
                if len(self.poll_statuses) > 1
                else self.poll_statuses[0]
            )
            batch: dict[str, Any] = {"id": "b1", "processing_status": status}
            if status == "ended":
                batch["results_url"] = self.results_url
            return json.dumps(batch).encode()
        raise AssertionError(f"unexpected call: {method} {url}")


def _client(transport: FakeTransport) -> AnthropicBatchClient:
    client = AnthropicBatchClient("test-key")
    # _http_raw is the documented transport seam for tests.
    client._http_raw = transport  # type: ignore[method-assign]
    return client


class TestClientValidation:
    def test_empty_api_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            AnthropicBatchClient("")

    def test_non_http_base_url_rejected(self) -> None:
        with pytest.raises(ValueError, match="http"):
            AnthropicBatchClient("k", base_url="ftp://example.com")

    async def test_create_batch_rejects_empty_requests(self) -> None:
        client = _client(FakeTransport([]))
        with pytest.raises(ValueError, match="no requests"):
            await client.create_batch([])

    async def test_fetch_results_rejects_non_http_url(self) -> None:
        client = _client(FakeTransport([]))
        with pytest.raises(ProviderError, match="scheme"):
            await client.fetch_results("file:///etc/passwd")

    async def test_malformed_results_line_raises(self) -> None:
        transport = FakeTransport([])
        client = _client(transport)

        def _bad(method: str, url: str, body: bytes | None) -> bytes:
            return b'{"ok": true}\nnot json\n'

        client._http_raw = _bad  # type: ignore[method-assign]
        with pytest.raises(ProviderError, match="line 2"):
            await client.fetch_results(_RESULTS_URL)


class TestHttpErrorMapping:
    def test_429_maps_to_rate_limit_with_retry_after(self) -> None:
        error = _map_http_error(429, "slow down", 7.5)
        assert isinstance(error, RateLimitError)
        assert error.retry_after == 7.5

    def test_other_statuses_map_to_provider_error(self) -> None:
        error = _map_http_error(500, "boom", 1.0)
        assert isinstance(error, ProviderError)
        assert "HTTP 500" in str(error)


class TestConsensusBatch:
    async def test_majority_happy_path(self) -> None:
        transport = FakeTransport(
            [
                _succeeded_line("consensus-0", "Paris"),
                _succeeded_line("consensus-1", "Paris"),
                _succeeded_line("consensus-2", "London"),
            ]
        )
        client = _client(transport)
        result = await consensus_batch(
            client, "claude-x", "Capital of France?", num_samples=3, poll_interval=0.0
        )
        assert result.value == "Paris"
        assert result.score == pytest.approx(2 / 3)
        assert result.metadata["batch_id"] == "b1"
        assert result.metadata["unique_responses"] == 2
        # Usage is summed across all three entries; llm_calls counts entries.
        assert result.cost.input_tokens == 30
        assert result.cost.output_tokens == 15
        assert result.cost.llm_calls == 3

    async def test_submitted_requests_carry_model_and_prompt(self) -> None:
        transport = FakeTransport([_succeeded_line("consensus-0", "hi")])
        client = _client(transport)
        await consensus_batch(
            client, "claude-x", "hello", num_samples=1, poll_interval=0.0
        )
        assert transport.created_payload is not None
        request = transport.created_payload["requests"][0]
        assert request["custom_id"] == "consensus-0"
        assert request["params"]["model"] == "claude-x"
        assert request["params"]["messages"][0]["content"] == "hello"

    async def test_unanimous_disagreement_raises(self) -> None:
        transport = FakeTransport(
            [
                _succeeded_line("consensus-0", "Paris"),
                _succeeded_line("consensus-1", "London"),
            ]
        )
        client = _client(transport)
        with pytest.raises(ConsensusFailedError):
            await consensus_batch(
                client,
                "claude-x",
                "q",
                num_samples=2,
                strategy="unanimous",
                poll_interval=0.0,
            )

    async def test_errored_entry_raises_with_custom_id(self) -> None:
        transport = FakeTransport(
            [
                _succeeded_line("consensus-0", "Paris"),
                _errored_line("consensus-1"),
            ]
        )
        client = _client(transport)
        with pytest.raises(ProviderError, match="consensus-1 \\(errored\\)"):
            await consensus_batch(
                client, "claude-x", "q", num_samples=2, poll_interval=0.0
            )

    async def test_num_samples_below_one_rejected(self) -> None:
        client = _client(FakeTransport([]))
        with pytest.raises(ValueError, match="num_samples"):
            await consensus_batch(client, "claude-x", "q", num_samples=0)

    async def test_polls_until_ended(self) -> None:
        transport = FakeTransport(
            [_succeeded_line("consensus-0", "hi")],
            poll_statuses=["in_progress", "in_progress", "ended"],
        )
        client = _client(transport)
        result = await consensus_batch(
            client, "claude-x", "q", num_samples=1, poll_interval=0.0
        )
        assert result.value == "hi"
        poll_calls = [
            call
            for call in transport.calls
            if call[0] == "GET" and "results" not in call[1]
        ]
        assert len(poll_calls) == 3

    async def test_poll_timeout_raises(self) -> None:
        transport = FakeTransport(
            [_succeeded_line("consensus-0", "hi")], poll_statuses=["in_progress"]
        )
        client = _client(transport)
        with pytest.raises(ProviderError, match="did not end within"):
            await consensus_batch(
                client, "claude-x", "q", num_samples=1, poll_interval=0.0, timeout=0.0
            )

    async def test_missing_results_url_raises(self) -> None:
        transport = FakeTransport(
            [_succeeded_line("consensus-0", "hi")], results_url=None
        )
        client = _client(transport)
        with pytest.raises(ProviderError, match="without a results_url"):
            await consensus_batch(
                client, "claude-x", "q", num_samples=1, poll_interval=0.0
            )

    async def test_results_missing_an_id_raises(self) -> None:
        # Batch "ends" but the results file only covers one of two requests.
        transport = FakeTransport([_succeeded_line("consensus-0", "hi")])
        client = _client(transport)
        with pytest.raises(ProviderError, match="missing 'consensus-1'"):
            await consensus_batch(
                client, "claude-x", "q", num_samples=2, poll_interval=0.0
            )


class TestMapBatch:
    async def test_results_return_in_prompt_order_despite_shuffled_file(self) -> None:
        transport = FakeTransport(
            [
                _succeeded_line("map-2", "third"),
                _succeeded_line("map-0", "first"),
                _succeeded_line("map-1", "second"),
            ]
        )
        client = _client(transport)
        result = await map_batch(
            client, "claude-x", ["p0", "p1", "p2"], poll_interval=0.0
        )
        assert result.value == ("first", "second", "third")
        assert result.score is None
        assert result.metadata["num_requests"] == 3

    async def test_temperature_omitted_unless_given(self) -> None:
        transport = FakeTransport([_succeeded_line("map-0", "x")])
        client = _client(transport)
        await map_batch(client, "claude-x", ["p"], poll_interval=0.0)
        assert transport.created_payload is not None
        assert "temperature" not in transport.created_payload["requests"][0]["params"]

    async def test_empty_prompts_rejected(self) -> None:
        client = _client(FakeTransport([]))
        with pytest.raises(ValueError, match="non-empty"):
            await map_batch(client, "claude-x", [])

    async def test_failed_entry_raises(self) -> None:
        transport = FakeTransport(
            [_succeeded_line("map-0", "ok"), _errored_line("map-1")]
        )
        client = _client(transport)
        with pytest.raises(ProviderError, match="map-1"):
            await map_batch(client, "claude-x", ["a", "b"], poll_interval=0.0)


class TestResultEntryParsing:
    async def test_multiple_text_blocks_concatenate(self) -> None:
        line = {
            "custom_id": "consensus-0",
            "result": {
                "type": "succeeded",
                "message": {
                    "content": [
                        {"type": "text", "text": "Hello, "},
                        {"type": "tool_use", "id": "t1"},
                        {"type": "text", "text": "world"},
                    ],
                    "usage": {"input_tokens": 1, "output_tokens": 2},
                },
            },
        }
        transport = FakeTransport([line])
        client = _client(transport)
        result = await consensus_batch(
            client, "claude-x", "q", num_samples=1, poll_interval=0.0
        )
        assert result.value == "Hello, world"

    async def test_malformed_message_counts_as_failure(self) -> None:
        line = {"custom_id": "consensus-0", "result": {"type": "succeeded"}}
        transport = FakeTransport([line])
        client = _client(transport)
        with pytest.raises(ProviderError, match="malformed_message"):
            await consensus_batch(
                client, "claude-x", "q", num_samples=1, poll_interval=0.0
            )
