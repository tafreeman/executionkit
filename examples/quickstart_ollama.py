"""Quickstart: consensus with Ollama (local, no API key needed).

Requires Ollama running locally with the llama3.2 model pulled:
    ollama pull llama3.2
    ollama serve

Run:
    python examples/quickstart_ollama.py
"""

import asyncio

from executionkit import Provider, consensus


async def main() -> None:
    provider = Provider(
        base_url="http://localhost:11434/v1",
        model="llama3.2",
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
