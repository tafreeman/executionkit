# ADR-005: Require callers to supply price rates

- Status: Accepted
- Date: 2026-05-22

## Context

ExecutionKit records token counts. Provider prices change by model, account,
region, cache behavior, and batch mode.

## Decision

`estimate_cost()` performs arithmetic with caller-supplied per-token input and
output rates. The package does not contain a price table or infer a currency.

## Consequences

- Cost estimates do not become stale because of a bundled table.
- The caller must load current rates and account for provider-specific billing.
- `TokenUsage` remains the stable accounting value.
- `estimate_cost()` does not validate whether rates match the selected model.

## Rejected alternatives

A built-in table would be convenient but could silently produce incorrect
estimates after a price or model change.
