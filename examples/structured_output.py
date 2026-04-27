"""Minimal structured-output example for ExecutionKit."""

from __future__ import annotations

import os

from executionkit import Provider, structured


async def main() -> None:
    provider = Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    )
    result = await structured(
        provider,
        "Return a JSON object with keys 'summary' and 'confidence' for ExecutionKit.",
    )
    print(result.value)
