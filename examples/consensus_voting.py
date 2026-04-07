"""Consensus voting strategies: MAJORITY vs UNANIMOUS.

Demonstrates num_samples, temperature, and both VotingStrategy values.

Run:
    OPENAI_API_KEY=sk-... python examples/consensus_voting.py
"""

import asyncio
import os

from executionkit import Provider, consensus
from executionkit.types import VotingStrategy


async def majority_example(provider: Provider) -> None:
    print("--- MAJORITY voting (default) ---")
    result = await consensus(
        provider,
        "Classify the sentiment of this review as POSITIVE, NEGATIVE, or NEUTRAL:\n"
        "'The product works well but shipping took forever.'",
        num_samples=5,
        strategy=VotingStrategy.MAJORITY,
        temperature=0.8,
    )
    print(f"Decision:    {result}")
    print(f"Agreement:   {result.metadata['agreement_ratio']:.0%}")
    print(f"Unique resp: {result.metadata['unique_responses']}")
    print(f"Ties:        {result.metadata['tie_count']}")
    print(f"Cost:        {result.cost}")
    print()


async def unanimous_example(provider: Provider) -> None:
    print("--- UNANIMOUS voting ---")
    print("(Raises ConsensusFailedError if any response differs.)")
    try:
        result = await consensus(
            provider,
            "What is 2 + 2? Reply with only the number.",
            num_samples=3,
            strategy=VotingStrategy.UNANIMOUS,
            temperature=0.0,
        )
        print(f"Decision:  {result}")
        print(f"Agreement: {result.metadata['agreement_ratio']:.0%}")
        print(f"Cost:      {result.cost}")
    except Exception as exc:
        print(f"Consensus failed: {exc}")
    print()


async def low_temperature_example(provider: Provider) -> None:
    print("--- MAJORITY with low temperature (more consistent) ---")
    result = await consensus(
        provider,
        "What programming language was created by Guido van Rossum?",
        num_samples=5,
        strategy="majority",
        temperature=0.2,
    )
    print(f"Answer:    {result}")
    print(f"Agreement: {result.metadata['agreement_ratio']:.0%}")
    print(f"Cost:      {result.cost}")
    print()


async def main() -> None:
    provider = Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    )

    await majority_example(provider)
    await unanimous_example(provider)
    await low_temperature_example(provider)


if __name__ == "__main__":
    asyncio.run(main())
