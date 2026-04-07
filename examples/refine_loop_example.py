"""Refine loop: iterative improvement with convergence tracking.

Shows the default LLM-based evaluator and a custom evaluator function.
Demonstrates score_history and converged metadata.

Run:
    OPENAI_API_KEY=sk-... python examples/refine_loop_example.py
"""

import asyncio
import os

from executionkit import Provider, refine_loop
from executionkit.provider import LLMProvider
from executionkit.types import TokenUsage


async def default_evaluator_example(provider: Provider) -> None:
    print("--- Default LLM evaluator ---")
    result = await refine_loop(
        provider,
        "Explain the difference between a process and a thread in one paragraph.",
        target_score=0.85,
        max_iterations=4,
    )
    print(f"Result:\n{result}\n")
    print(f"Score:        {result.score:.2f}")
    print(f"Iterations:   {result.metadata['iterations']}")
    print(f"Converged:    {result.metadata['converged']}")
    print(f"Score history: {[f'{s:.2f}' for s in result.metadata['score_history']]}")
    print(f"Cost:         {result.cost}")
    print()


async def custom_evaluator_example(provider: Provider) -> None:
    print("--- Custom evaluator: word-count quality heuristic ---")

    # A custom evaluator that scores based on response length and keyword presence.
    # Real evaluators would use domain-specific rubrics or a judge model.
    async def length_evaluator(text: str, llm: LLMProvider) -> float:
        words = text.split()
        word_count = len(words)

        # Target: 50-150 words scores highest
        if word_count < 20:
            length_score = word_count / 20.0
        elif word_count <= 150:
            length_score = 1.0
        else:
            length_score = max(0.0, 1.0 - (word_count - 150) / 200.0)

        # Bonus for technical keywords
        keywords = ["cpu", "memory", "kernel", "context", "switch", "schedule"]
        keyword_score = min(
            1.0,
            sum(1 for kw in keywords if kw in text.lower()) / 3.0,
        )

        return 0.6 * length_score + 0.4 * keyword_score

    result = await refine_loop(
        provider,
        "Explain the difference between a process and a thread.",
        evaluator=length_evaluator,
        target_score=0.9,
        max_iterations=3,
        max_cost=TokenUsage(input_tokens=10000, output_tokens=5000, llm_calls=10),
    )

    print(f"Result:\n{result}\n")
    print(f"Score:         {result.score:.2f}")
    print(f"Iterations:    {result.metadata['iterations']}")
    print(f"Converged:     {result.metadata['converged']}")
    print(f"Score history: {[f'{s:.2f}' for s in result.metadata['score_history']]}")
    print(f"Cost:          {result.cost}")
    print()


async def main() -> None:
    provider = Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    )

    await default_evaluator_example(provider)
    await custom_evaluator_example(provider)


if __name__ == "__main__":
    asyncio.run(main())
