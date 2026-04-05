# Review Iteration 3 — Final Pass

## Market Resilience (opus)

### 12-Month Survival: YES
Providers absorbing single-call reasoning (o3, Claude extended thinking) but NOT multi-call orchestration (voting, refinement with convergence, cross-pattern budget tracking). ExecutionKit patterns remain unaddressed through April 2027.

### pipe() Paradox: KEEP BUT DEMOTE
Anti-framework movement is strong, but pipe() solves real problems (budget tracking across patterns, partial results). Hero example should be single pattern (consensus), not pipe().

### tree_of_thought Deferral: CONFIRMED
ToT remains mostly academic. Recent adaptive pruning research (26-75% token savings) makes it more viable but cutting-edge. Defer to v0.2.

### Market Size: NARROW BUT REAL
Developer bifurcation: Camp 1 ("just use SDK") growing, will never use ExecutionKit. Camp 2 ("composable primitives") proven by DSPy's 23K stars. ExecutionKit targets the subset wanting a la carte patterns without DSPy's full framework. Plan for hundreds of users.

### Final Pattern Lineup
- SHIP: consensus, refine_loop, react_loop, pipe()
- DEFER: tree_of_thought (v0.2)
- 90-day kill condition: <50 stars and zero production evidence → archive

## Technical Readiness (sonnet)

### All 5 Blockers Resolved

| Blocker | Fix |
|---------|-----|
| LLMChunk undefined | Add `@dataclass class LLMChunk: delta: str; finish_reason: str | None = None` |
| _subtract() missing | Add 5-line function with `max(0, ...)` clamping |
| UnsupportedContentError missing | Add under LLMError branch (3 lines) |
| RetryConfig unspecified | Full dataclass with max_retries, base_delay, exponential_base, should_retry(), get_delay() |
| pipe() empty steps crash | Guard: `if not steps: return PatternResult(value=prompt)` |

### All 7 mypy Failures Resolved

| Issue | Fix |
|-------|-----|
| TypeAlias missing | `Evaluator: TypeAlias = Callable[...]` |
| __iter__ return type | Delete __iter__ (cut per scope razor) OR annotate `-> Iterator[Any]` |
| consensus T unbound | Implementation returns `PatternResult[Any]`; overloads provide precise types |
| ToolCallingProvider drops parent kwargs | Keep temperature/max_tokens in child, add tools alongside |
| T undefined in retry.py | Add `T = TypeVar("T")` |
| Missing return when max_retries=0 | Guard: `if max_retries == 0: return await fn(...)` |
| Bare PatternResult | Use `PatternResult[Any]` in compose.py and kit.py |

### Error Hierarchy (Final — 9 classes)

```
ExecutionKitError
  LLMError
    RateLimitError        (retryable)
    PermanentError        (auth, not-found — NOT retried)
    ProviderError         (catch-all retryable)
  PatternError
    BudgetExhaustedError
    MaxIterationsError
    ConsensusFailedError
```

### Highest Risk: providers/_ollama.py + json_extraction.py
Ollama doesn't enforce response_format for all models. json_extraction is the safety net. asyncio.to_thread + stdlib urllib has no connection pooling. Test mocking requires care.

### Verdict: READY TO BUILD

## Final Scope Lock (haiku)

### IN (ship in v0.1)

| Category | Items |
|----------|-------|
| Patterns | consensus, refine_loop, react_loop |
| Composition | pipe() |
| Session | Kit |
| Providers | OpenAI, Ollama, Mock |
| Engine | retry, parallel (both), convergence, json_extraction |
| Types | PatternResult (4 fields: value/cost/score/metadata), TokenUsage, Tool, ToolCall, VotingStrategy (MAJORITY/UNANIMOUS), Evaluator, PatternStep |
| Errors | 9 classes (3 roots + 6 leaves including PermanentError) |
| Infrastructure | CLI, pyproject metadata, 5 examples, CONTRIBUTING.md |
| Features | CostTracker, checked_complete, validate_score, agreement_ratio, was_truncated |

### OUT (defer to v0.2)

| Category | Items |
|----------|-------|
| Patterns | tree_of_thought |
| Providers | Anthropic, _conversion.py |
| Types | TraceEntry, ProgressCallback, request_id, started_at, per-call usage |
| Features | max_trace_entries, max_concurrency on ToT, StreamingProvider, default max_cost |
| Infrastructure | mkdocs site, ruff D enforcement, 10→5 examples |

## GO/NO-GO: GO

All blockers resolved. Market validated. Scope locked. Estimated 7-8 days for Tier 2.
