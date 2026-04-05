# ExecutionKit MVP Definition — Summary

**Documents created:**
1. `MVP_TIERS.md` — Complete breakdown of TIER 1, 2, 3 with file lists, LOC estimates, and verification gates
2. `SHIP_DECISION.md` — Risk assessment, timeline comparison, market signal analysis, and recommendation
3. `TIER1_SCAFFOLD.md` — Exact code you can copy-paste tomorrow to ship Friday

---

## The Question You Asked

> What is the absolute smallest thing you could ship that proves the concept?

**Answer: TIER 1 — One pattern (consensus), one provider (OpenAI), ~250 LOC, 3-4 files, tomorrow.**

---

## The Three Tiers at a Glance

| Dimension | TIER 1 | TIER 2 | TIER 3 |
|-----------|--------|--------|--------|
| **Ship Date** | Tomorrow (Friday) | This week (Wednesday) | This month (2.5 weeks) |
| **Core LOC** | ~250 | ~1700 | ~3000 |
| **Files** | 3-4 core | ~7 | ~12 |
| **Patterns** | 1 (consensus) | 4 | 4 |
| **Providers** | 1 (OpenAI) | 2 (+ Ollama) | 4 (+ Anthropic, Mock) |
| **Composition** | None | None | pipe() |
| **Tracing** | None | None | Deferred to v0.2 |
| **Docs** | Minimal | Good | Complete |
| **Message Conversion** | None | None | 250 LOC (hardest part) |

---

## Why TIER 2 is Recommended

1. **Sweet spot.** All 4 core patterns (validated by Iteration 1) + 2 providers (proves design) in 3-4 days vs. 1 day (TIER 1) or 8-10 days (TIER 3).

2. **Ship message.** "Four patterns that work, two providers to prove it" > "one consensus pattern" but much more credible than "comprehensive library with Anthropic."

3. **No conversion complexity.** Skip Anthropic's message format edge cases. Ship v0.2 with Anthropic + pipe() based on actual demand.

4. **Testable.** 80% coverage across 4 patterns is achievable. 16-combo provider matrix is overkill for v0.1.

5. **Clear roadmap.** "v0.1: core patterns. v0.2: Anthropic + composition. v0.3: streaming + observability." Users understand the story.

---

## What Each Tier Proves

### TIER 1 Proves
- ✅ Voting logic works
- ✅ Token tracking works
- ✅ API is intuitive
- ❌ Other patterns are stable
- ❌ Provider-agnostic design works
- ❌ Composability works

### TIER 2 Proves
- ✅ Voting, refinement, branching, tool calling all work
- ✅ Two providers shows abstraction is real
- ✅ All 4 patterns deserve to exist
- ✅ Cost tracking across all patterns works
- ❌ Composability works
- ❌ Anthropic support needed

### TIER 3 Proves
- ✅ Everything TIER 2 + composability
- ✅ Anthropic integration works
- ✅ Message conversion is bulletproof
- ✅ Library is production-ready
- ✅ Genuine moat (pipe() + budget tracking)

---

## Decision Framework

**Ship TIER 1 if:**
- You want feedback in 48 hours
- You're unsure which patterns matter
- Your team is <3 people
- You can say "alpha" and mean it

**Ship TIER 2 if:**
- You want "professional v0.1" on day one
- All 4 patterns are must-haves
- You have 3-4 days
- Anthropic is v0.2 (not required)

**Ship TIER 3 if:**
- Anthropic is strategic (enterprise deals)
- pipe() composability is the main story
- You have 8-10 days
- 3000+ LOC is manageable

**Recommendation: Ship TIER 2.** Professional, feature-complete, credible roadmap, 3-4 days of work.

---

## Iteration 1 Cuts Applied

The plan was over-engineered. Here's what we cut to reach MVP:

| Item | TIER 1 | TIER 2 | TIER 3 | Rationale |
|------|--------|--------|--------|-----------|
| TraceEntry (9 fields) | ❌ | ❌ | ✅ v0.2 | Observability, not core behavior |
| ProgressCallback | ❌ | ❌ | ✅ v0.2 | Requires tracing |
| PatternResult | ❌ | ✅ | ✅ | Simplified: value + cost + score + metadata |
| VotingStrategy enum | ❌ | ❌ | ✅ | Default "majority" only. Accept string override. |
| ConvergenceDetector | ❌ | ❌ | ✅ v0.2 | Replace with simple max_iterations |
| json_extraction | ❌ | ❌ | ❌ v0.2 | Band-aid for messy output |
| Anthropic + _conversion | ❌ | ❌ | ✅ | 250 LOC maintenance tax → v0.2 |
| Error hierarchy (10 classes) | ✅ 4 | ✅ 6 | ✅ 8 | Minimal set: ExecutionKitError, LLMError, RateLimitError, BudgetExhaustedError |
| on_progress param | ❌ | ❌ | ✅ | Requires TraceEntry |
| max_trace_entries | ❌ | ❌ | ✅ | Requires TraceEntry |
| 25 source files | ❌ | ✅ 7 | ✅ 12 | Consolidated: patterns in 1-2 files, engine in 1 file |
| RetryConfig | ❌ | ✅ v0.2 | ✅ v0.2 | Document "wrap with tenacity if needed" |

---

## Exact Files for Each Tier

### TIER 1 (3-4 files)
```
src/executionkit/
  __init__.py         # consensus + sync wrapper + exports
  _core.py            # LLMProvider protocol + LLMResponse + consensus + OpenAI
  _errors.py          # 4 errors
tests/
  conftest.py         # MockProvider
  test_consensus.py   # 80+ test cases
examples/
  quickstart_consensus.py
```

### TIER 2 (7 files)
```
src/executionkit/
  __init__.py         # all exports + sync wrappers
  provider.py         # LLMProvider + ToolCallingProvider + LLMResponse + errors
  types.py            # PatternResult + TokenUsage + Tool
  patterns.py         # consensus + refine_loop + tree_of_thought + react_loop (or split)
  _core.py            # checked_complete + gather_resilient + helpers
  providers/
    __init__.py       # lazy imports
    _openai.py
    _ollama.py
tests/
  test_consensus.py
  test_refine_loop.py
  test_tree_of_thought.py
  test_react_loop.py
  test_providers.py
examples/
  quickstart_openai.py
  quickstart_ollama.py
  (5 more examples)
```

### TIER 3 (12 files)
```
(everything in TIER 2, plus:)
src/executionkit/
  compose.py          # pipe()
  kit.py              # Kit session object
  engine/
    __init__.py
    parallel.py       # gather_resilient + gather_strict (public)
    retry.py          # RetryConfig + with_retry (public)
  providers/
    _anthropic.py
    _conversion.py    # 250 LOC for 9 edge cases
    _mock.py
docs/
  (mkdocs setup + 5 pages)
CONTRIBUTING.md
(10 total examples)
```

---

## Verification Gates (Must Pass Before Shipping)

### TIER 1 Gate
```
✅ ruff check && ruff format --check
✅ mypy --strict src/
✅ pytest --cov-fail-under=80 (integration tests excluded)
✅ examples/quickstart_consensus.py runs with real API key
✅ examples/quickstart_consensus.py works in Jupyter (async wrapper tested)
✅ Zero hardcoded secrets, .env in .gitignore
✅ README complete with hero example + "coming soon" roadmap
```

### TIER 2 Gate
```
(all TIER 1, plus:)
✅ All 4 patterns work with OpenAI
✅ All 4 patterns work with Ollama
✅ 5 examples run end-to-end (consensus, refine, tree, react, custom provider)
✅ Agreement ratio computed correctly for consensus
✅ Tool timeouts work in react_loop
✅ Evaluators work in refine_loop and tree_of_thought
✅ Default evaluators use LLM (simple 0-10 score)
```

### TIER 3 Gate
```
(all TIER 2, plus:)
✅ Anthropic provider works
✅ Message conversion round-trips all 9 edge cases
✅ pipe() merges costs correctly
✅ pipe() passes remaining budget to each step
✅ pipe() handles partial failures
✅ 10 examples all run
✅ CONTRIBUTING.md is complete
✅ mkdocs builds without errors
✅ Full test coverage >80%
```

---

## Estimated Effort

| Task | Duration | Who | Output |
|------|----------|-----|--------|
| TIER 1 build | 4 hours | 1 person | v0.1.0-alpha on PyPI |
| TIER 1 → TIER 2 (parallel 2 people) | 3-4 days | 2 people | v0.1.0-beta on PyPI |
| TIER 2 → TIER 3 (parallel 2 people) | 5-6 days | 2 people | v0.1.0 on PyPI |

---

## Roadmap Beyond v0.1

### v0.1.0-alpha → v0.1.0-beta → v0.1.0 (This Month)
- TIER 1 → TIER 2 → TIER 3 progression
- Lock API for 1.0

### v0.2 (Next Month)
- AnthropicProvider (Iteration 1 cut)
- StreamingProvider (Iteration 1 cut)
- TraceEntry + ProgressCallback (Iteration 1 cut)
- RetryConfig wrapper (currently document "use tenacity")
- OpenTelemetry integration

### v0.3 (2 Months Out)
- Multi-modal content in message converter
- Additional composition operators
- Custom pattern scaffolding guide
- Performance profiling + optimization

---

## Next Steps

1. **Read `MVP_TIERS.md`** for full technical breakdown of each tier.
2. **Read `SHIP_DECISION.md`** for risk analysis and timeline comparison.
3. **Read `TIER1_SCAFFOLD.md`** if you decide to ship TIER 1 Friday.
4. **Make a decision:** TIER 1 (tomorrow), TIER 2 (this week), or TIER 3 (this month)?
5. **Start coding:** Copy files from `TIER1_SCAFFOLD.md` or adapt for your chosen tier.

---

## Key Insights from Iteration 1 Review

**The plan had 5 code blockers, 7 mypy failures, and 3 logic issues.** We fixed all of them by cutting unnecessary scope.

**The genuine moat is composability (pipe() + budget tracking),** not individual patterns. But customers need to trust individual patterns first. Prove patterns work standalone (TIER 2), then add composition (TIER 3).

**Anthropic is optional for v0.1.** Message conversion is complex (250 LOC, 9 edge cases). OpenAI + Ollama + Mock is enough to prove the design. Ship Anthropic in v0.2 based on actual demand.

**Tracing/observability is v0.2.** TraceEntry, ProgressCallback, ConvergenceDetector all deferred. Ship simple, proven patterns first.

---

## The Recommendation

**Ship TIER 2 by end of week.**

- Proves all 4 core patterns work
- Validates provider-agnostic design with 2 providers
- Ship message is clear: "Production-ready pattern library"
- Defers Anthropic + composition to v0.2 based on feedback
- 3-4 days of work, 1700 LOC, defensible scope

This balances speed (TIER 1's 1 day) with credibility (TIER 3's full vision).

Good luck. You've got this.
