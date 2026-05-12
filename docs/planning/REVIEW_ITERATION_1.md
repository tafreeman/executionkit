# Review Iteration 1 — April 2026

## Market & Feasibility (opus)

### Pattern Ratings

| Pattern | Rating | Evidence |
|---------|--------|----------|
| **tree_of_thought** | STILL RELEVANT | No production-quality competitor. `tree-of-thoughts` PyPI is research-grade. DSPy has BestOfN but no beam search. Native reasoning (o3, Claude extended thinking) is single-call, not multi-branch. |
| **react_loop** | THREATENED | Most crowded space. OpenAI Agents SDK, Claude Agent SDK, LangGraph `create_react_agent()`, DSPy `dspy.ReAct` all exist. Slim differentiation. |
| **consensus** | STILL RELEVANT | No standalone voting library on PyPI. DSPy BestOfN lacks voting strategies and agreement_ratio. Hermes-agent issue #412 validates demand. |
| **refine_loop** | STILL RELEVANT | DSPy `dspy.Refine` is closest competitor but couples to DSPy's module system. No standalone provider-agnostic refinement loop on PyPI. |

### Key Competitive Developments
- **DSPy** now has `BestOfN`, `Refine`, `ReAct`, `ChainOfThought` built-in — single biggest threat
- **OpenAI Agents SDK** (March 2025) and **Claude Agent SDK** both have built-in ReAct loops
- **Google Cascades**: Composable LM patterns library — monitor closely
- Native reasoning (o3, Claude extended thinking, Gemini Deep Think) reduces demand for simple CoT but NOT for multi-call orchestration (branching, voting, iteration)

### Strategic Recommendations
1. Lead with **tree_of_thought + consensus** (least competition)
2. Position react_loop as composition primitive, not headline feature
3. Composability via pipe() is the genuine moat — no competitor offers cross-pattern budget tracking

## Technical Feasibility (sonnet)

### 5 Blockers Found

| # | File | Issue |
|---|------|-------|
| 1 | provider.py | `LLMChunk` undefined — StreamingProvider references it, causes NameError |
| 2 | compose.py | `_subtract()` called but never defined |
| 3 | providers/_conversion.py | `UnsupportedContentError` not in error hierarchy |
| 4 | engine/retry.py | `RetryConfig` class fields/methods never specified |
| 5 | compose.py | `pipe()` crashes on empty `steps` (result is None) |

### 7 mypy --strict Failures

| # | File | Issue |
|---|------|-------|
| 6 | types.py | `Evaluator`/`ProgressCallback` need `TypeAlias` annotation |
| 7 | types.py | `__iter__` missing return type annotation |
| 8 | consensus.py | `T` unbound when `response_format=None` |
| 9 | provider.py | `ToolCallingProvider.complete()` drops parent kwargs — incompatible override |
| 10 | retry.py | `T` used without TypeVar declaration |
| 11 | retry.py | Missing return path when `max_retries=0` |
| 12 | compose.py, kit.py | Bare `PatternResult` without type parameter |

### 3 Logic Issues

| # | File | Issue |
|---|------|-------|
| 13 | base.py | `llm_calls` budget field never checked in `checked_complete` |
| 14 | provider.py | `list[ToolCall]` on frozen dataclass is still mutable |
| 15 | parallel.py | `gather_strict` calls `len(coros)` — fails on generators |

### Source Path Bug
- Plan references `agentic-workflows-v2/agentic_v2/tools/llm/provider_adapters.py` — WRONG
- Actual path: `D:\source\prompts\tools\llm\provider_adapters.py` (monorepo root)
- File is sync + string-based — NOT compatible with async LLMProvider. Cannot be reused. Start from scratch.

## Scope Razor (haiku)

### Recommended Cuts

| Item | Action | Rationale |
|------|--------|-----------|
| TraceEntry (9 fields) | CUT entirely | Observability, not core behavior. v0.2. |
| ProgressCallback | CUT | Same. v0.2. |
| PatternResult fields | CUT 3 | Remove `iterations`, `trace`, `request_id`. Keep `value`, `cost`, `score`, `metadata`. |
| VotingStrategy enum | CUT | Default "majority" only. Accept string override. |
| ConvergenceDetector | SIMPLIFY | Replace with plain `max_iterations` check. |
| json_extraction.py | CUT | Band-aid for messy output. v0.2. |
| Anthropic + _conversion.py | CUT | 250 LOC maintenance tax. OpenAI + Ollama covers 80%+. v0.2. |
| Error hierarchy (10 classes) | CUT to 4 | Keep ExecutionKitError, BudgetExhaustedError, MaxIterationsError, RateLimitError. |
| on_progress param | CUT from all patterns | No trace = no progress callback. |
| max_trace_entries param | CUT from all patterns | No trace = no bound needed. |
| 25 source files | CONSOLIDATE to ~11 | engine/ → 1 file, patterns/ → 1 file or keep separate, examples → 3-5 |

## GO/NO-GO

**CONDITIONAL GO.** The 4 patterns are market-validated. But the plan has 5 code blockers, 7 mypy failures, and ~30% remaining over-engineering. Fix blockers and apply scope cuts before starting Phase 1a.
