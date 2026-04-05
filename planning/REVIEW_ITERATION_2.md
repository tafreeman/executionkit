# Review Iteration 2 — Deep Validation of Iteration 1 Cuts

## Market Deep Dive (opus)

### DSPy Head-to-Head

| Feature | DSPy | ExecutionKit |
|---------|------|-------------|
| Consensus/Voting | `dspy.majority` simple plurality. `BestOfN` picks best by reward. No voting strategies, no agreement_ratio. | Majority/unanimous. Agreement metrics. Budget tracking. |
| Refinement | `dspy.Refine` loops N times with LLM feedback. NO convergence detection. | ConvergenceDetector with patience, delta, target score. Early exit saves LLM calls. |
| ReAct | `dspy.ReAct` built-in, mature, coupled to DSPy signatures. | Provider-agnostic but crowded space. |
| Composition | DSPy `>>` operator, built-in optimization. | pipe() enables cross-pattern composition with shared budget. |

**Key finding:** ConvergenceDetector IS a real differentiator vs DSPy Refine. Iteration 1 recommended cutting it — WRONG.

### react_loop Viability
Most crowded space. Without pipe(), react_loop's only differentiator is cost tracking. With pipe(), it becomes "the composable agent loop" — genuinely novel.

### Google Cascades — DEAD
Research prototype from 2022, 219 stars, unmaintained. Not a threat.

### LLM Voting in Production
ZenML analysis of 1,200+ deployments: ZERO examples of voting/self-consistency in production. Dominant patterns: LLM-as-judge, deterministic validation, circuit breakers. Voting is pre-adoption — ExecutionKit would be creating the market.

### Pricing Risk
Cheap models ($0.05/M tokens): budget tracking is vanity. Frontier models ($5-15/M): multi-call patterns are expensive. Budget tracking matters for frontier tier and always will.

### Pattern Ship Recommendation
Ship 3 patterns + pipe() in v0.1. Defer tree_of_thought to v0.2 (most complex, least production-validated). Killer demo: `pipe(refine_loop, consensus)` on frontier model.

## Cut Safety Validation (sonnet)

| Cut | Verdict | Issue |
|-----|---------|-------|
| TraceEntry | UNSAFE as partial | pipe() accesses result.trace. Must cut atomically across compose.py + PatternResult + all patterns. |
| ProgressCallback | SAFE | Must precede or accompany TraceEntry cut. |
| ConvergenceDetector | UNSAFE to remove | Wastes 8 LLM calls per run. Inline the logic (5 lines) instead of cutting. |
| json_extraction.py | UNSAFE if Ollama kept | Ollama + response_format unreliable. json_extraction is the fallback. |
| Anthropic + _conversion.py | SAFE | ToolCall still needed for OpenAI. Remove Tool.to_anthropic_schema(). |
| Error hierarchy to 4 | UNSAFE | AuthN failures retry 3x with no PermanentError class. Need 5 minimum. |
| VotingStrategy enum | UNSAFE | String accepts invalid values silently. Enum costs 4 lines. |
| File consolidation | SAFE | No code exists yet. |

### Corrected Cuts (vs Iteration 1)

| Item | Iter 1 Said | Iter 2 Corrects |
|------|-------------|-----------------|
| ConvergenceDetector | CUT | KEEP — inline early-exit logic |
| json_extraction.py | CUT | KEEP — Ollama fallback |
| Error hierarchy | CUT to 4 | CUT to 5 — add PermanentError |
| VotingStrategy | CUT enum | KEEP enum — cut WEIGHTED only |
| pipe() | CUT | KEEP — it's the moat |

## Minimum Viable Tiers (haiku)

| Tier | Scope | LOC | Files | Timeline |
|------|-------|-----|-------|----------|
| 1 | consensus + OpenAI only | ~250 | 3-4 | Tomorrow |
| 2 | 3-4 patterns + 2 providers + pipe() | ~1,700 | 7-10 | This week |
| 3 | Full plan + Anthropic + docs site | ~3,000 | 25 | This month |

## GO/NO-GO

**GO for Tier 2 with corrections.** Fix 5 code blockers, keep ConvergenceDetector + json_extraction + VotingStrategy enum, add PermanentError to hierarchy. Consider deferring tree_of_thought to v0.2.
