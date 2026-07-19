---
tags:
  - recipe
  - composition
---

# Wrapping consensus inside iterative refinement

You want the **stability** of consensus voting *and* the **quality bar** of iterative refinement. Run consensus to get a draft, then refine that draft until it crosses your score gate.

## The pattern

Use `pipe()` with `consensus` followed by `refine_loop`. Costs accumulate; budget is shared.

```python
import asyncio
import os
from functools import partial
from executionkit import (
    Provider,
    TokenUsage,
    consensus,
    pipe,
    refine_loop,
)

async def main() -> None:
    async with Provider(
        base_url="https://api.openai.com/v1",
        api_key=os.environ["OPENAI_API_KEY"],
        model="gpt-4o-mini",
    ) as provider:
        result = await pipe(
            provider,
            "Write a one-paragraph executive summary of the Turing test "
            "for an audience of non-technical board members.",
            # Step 1: 5 parallel drafts, take the majority winner.
            partial(consensus, num_samples=5, temperature=0.9),
            # Step 2: refine the winner until score >= 0.9 or 3 iterations.
            partial(refine_loop, target_score=0.9, max_iterations=3),
            # End-to-end ceiling: hard cap at 20 LLM calls / 30K tokens.
            max_budget=TokenUsage(
                input_tokens=20_000,
                output_tokens=10_000,
                llm_calls=20,
            ),
        )

        print(result.value)                                  # final refined paragraph
        print(result.cost)                                   # cumulative cost across both steps
        print(result.metadata["step_count"])                 # 2
        for i, meta in enumerate(result.metadata["step_metadata"]):
            print(f"step {i}: {dict(meta)}")

asyncio.run(main())
```

## What happens, step by step

1. **Consensus runs first.** 5 parallel completions at `temperature=0.9`, normalized whitespace, majority vote. The winner becomes the input prompt for step 2. (`agreement_ratio` ends up in `step_metadata[0]` — useful if you want to gate refinement on confidence.)

2. **`pipe` computes remaining budget.** After step 1 spends `cost1`, step 2 receives `max_cost = max_budget - cost1`. If consensus burned 5 of the 20 LLM calls, refine_loop sees `max_cost.llm_calls = 15`.

3. **Refine_loop runs second.** It scores the consensus winner, then asks the model to improve it. Stops at `target_score=0.9`, after 3 iterations, or when budget runs out.

4. **Result.** `result.value` is the best refined paragraph. `result.cost` is the sum across both steps. If either step had raised `BudgetExhaustedError`, the exception's `.cost` would include the cumulative spend so far.

## Why this beats running them separately

- **One budget, not two.** `max_budget` is enforced *across* both steps. If consensus uses more than expected, refine_loop gets less.
- **Cumulative cost reporting.** You get one `TokenUsage` for the whole flow, not two you have to add up.
- **Errors carry the full spend.** If refine_loop raises mid-iteration, the exception's `.cost` includes the consensus tokens too.
- **One async call site.** No glue code threading outputs between calls.

## Variations

### Gate refinement on consensus confidence

`pipe` always runs every step. If you want to skip refinement when consensus already agrees strongly, write a tiny step that short-circuits:

```python
async def refine_only_if_uncertain(provider, prompt, **kw):
    # By the time this step runs, `prompt` is the consensus winner string.
    # Read step_metadata from the *previous* result by skipping pipe and writing
    # the orchestration ourselves:
    pass

# Hand-rolled version:
draft = await consensus(provider, original_prompt, num_samples=5)
if draft.score is not None and draft.score >= 0.95:
    final_value = draft.value
else:
    refined = await refine_loop(provider, draft.value, target_score=0.9)
    final_value = refined.value
```

This keeps cost low when consensus is already confident. Pipe is great for unconditional chains; for branches, write the async glue directly.

### Three-step pipe: classify → consensus → refine

```python
result = await pipe(
    provider,
    user_request,
    partial(consensus, num_samples=3,                 # 1. cheap classification
            temperature=0.0),
    partial(consensus, num_samples=5),                # 2. answer with voting
    partial(refine_loop, target_score=0.9),           # 3. polish
    max_budget=TokenUsage(llm_calls=30),
)
```

The first step's *output value* (the classification label) becomes the *input prompt* of step 2. That's only useful if step 2 can do something useful with the label as a prompt — usually you'd write step 2 to interpret it. Pipe is at its best when each step can take the previous step's stringified value as a sensible prompt.

## Caveats

- **Pipe threads `value` as the next prompt.** If step 1's value is structured (a number, a JSON blob), it'll be `str()`-ified. For non-string flows, write the orchestration without `pipe`.
- **`max_budget` is a ceiling, not a quota per step.** It says "across the whole chain, don't exceed this." Individual steps still have their own knobs (`num_samples`, `max_iterations`).
- **Step kwargs are filtered.** `pipe` introspects each step's signature and drops kwargs the step doesn't accept. This means typos in `**shared_kwargs` are silently dropped — verify with a small test if you're unsure.

## Related

- [Pipe pattern](../patterns/pipe.md) — full reference for the composition primitive.
- [Cost-aware routing](cost-routing.md) — pick a different provider per tier.
- [Multi-provider failover](failover.md) — fall through to a backup on rate limits.
