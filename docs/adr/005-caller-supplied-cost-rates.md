# ADR-005: Caller-Supplied Cost Rates over Built-in Price Table

**Date:** 2026-05-22
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** When implementing `cost.py` and `estimate_cost()`, the team explicitly chose not to embed a table of per-token prices and instead required callers to supply `input_rate` and `output_rate` directly.

---

## Context and Problem Statement

ExecutionKit tracks token usage across LLM calls (`CostTracker`) and enforces call budgets via `max_cost` parameters. A natural next step is to convert token counts into dollar estimates. Libraries in this space often ship a hard-coded pricing table keyed by model name (e.g. `{"gpt-4o": {"input": 5e-6, "output": 15e-6}, ...}`).

The team needed to decide whether `estimate_cost()` should look up rates from a built-in table or require them to be passed in by the caller.

## Decision Drivers

* LLM pricing changes frequently and varies by account tier, region, and promotional pricing — a bundled table is stale from the day it ships.
* ExecutionKit targets the OpenAI-compatible API format, not a fixed set of models. Any model on any compatible endpoint can be used; the library has no reliable way to map an arbitrary `model` string to a price.
* Embedding a pricing table creates a maintenance obligation: every price change or new model requires a library release.
* The `zero-runtime-dependency` constraint (ADR-004) precludes fetching live prices from a remote source.
* Callers always know what endpoint they are hitting and can read current prices from their provider's pricing page.

## Considered Options

* Option A: No built-in price table — `estimate_cost(usage, *, input_rate, output_rate)` requires caller-supplied rates
* Option B: Built-in price table keyed by model name, with a fallback to caller-supplied rates
* Option C: Built-in price table only; raise `ValueError` for unknown models

## Decision Outcome

**Chosen option:** Option A (caller-supplied rates), as implemented in `executionkit/cost.py`. The `estimate_cost()` function accepts a `TokenUsage` snapshot plus explicit `input_rate` and `output_rate` keyword arguments (per-token, in the same currency unit as the rates). It performs the arithmetic (`input_tokens * input_rate + output_tokens * output_rate`) and returns the result. The function ships no price table and performs no model-name lookup.

The module docstring for `cost.py` explicitly states: "ExecutionKit ships **no price table** — rates change and differ by account tier. Pass per-token rates from your provider's pricing page."

### Positive Consequences

* `estimate_cost()` never goes stale; the library does not need a release when a provider changes its pricing.
* Any model on any OpenAI-compatible endpoint works correctly — the caller supplies rates appropriate for their specific tier and region.
* The function is trivially testable: the expected output is deterministic given the inputs.
* No hidden assumptions about which models are "known" to the library.

### Negative Consequences

* Callers must look up rates themselves and pass them in on every call. This is a minor ergonomic cost.
* There is no guard against obviously wrong rates (e.g. negative values). The docstring notes that rates are "assumed non-negative and finite; no validation is performed."

## Pros and Cons of the Options

### Option A: Caller-supplied rates

* **Good:** Never stale — library releases are not needed for pricing changes.
* **Good:** Works with any model on any compatible endpoint.
* **Good:** Consistent with the zero-dependency principle (no network calls to fetch live prices).
* **Bad:** Callers must supply rates explicitly; there is no convenience default.

### Option B: Built-in table with fallback

* **Good:** Common models work without the caller knowing their rates.
* **Bad:** Table becomes stale immediately; incorrect estimates are worse than no estimates.
* **Bad:** Adds a maintenance obligation: each model or pricing change requires a release.
* **Bad:** Partial coverage (known vs. unknown models) creates inconsistent behaviour.

### Option C: Built-in table only, error on unknown

* **Good:** Prevents silent wrong estimates for unmapped models.
* **Bad:** Breaks for any model not in the table, which defeats the OpenAI-compatible-endpoint positioning.
* **Bad:** Same staleness and maintenance problems as Option B, with worse coverage.
