"""Quickstart: consensus with OpenAI.

Run:
    OPENAI_API_KEY=sk-... python examples/quickstart_openai.py
"""

import asyncio
import os

from executionkit import Provider, consensus


async def main() -> None:
    provider = Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    )

    result = await consensus(
        provider,
        "What is the capital of France?",
        num_samples=3,
    )

    print(f"Answer: {result}")
    print(f"Agreement: {result.metadata['agreement_ratio']:.0%}")
    print(f"Cost: {result.cost}")


if __name__ == "__main__":
    asyncio.run(main())
