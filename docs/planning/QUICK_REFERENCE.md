# ExecutionKit MVP — Quick Reference Card

Print this. Tape it to your monitor. Use it Friday.

---

## The Three Tiers (One Page)

```
┌─────────────────────────────────────────────────────────────────┐
│                    TIER 1: SHIP TOMORROW                        │
├─────────────────────────────────────────────────────────────────┤
│ Files: 3-4     │ Patterns: 1 (consensus)  │ Providers: 1 (OAI) │
│ LOC: ~250      │ Duration: 4 hours        │ Status: alpha      │
│ Ship: Friday   │ Signal: "We can ship"    │ Risk: Too minimal  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   TIER 2: SHIP THIS WEEK                        │
├─────────────────────────────────────────────────────────────────┤
│ Files: ~7      │ Patterns: 4 (all)        │ Providers: 2       │
│ LOC: ~1700     │ Duration: 3-4 days       │ Status: beta       │
│ Ship: Weds     │ Signal: "Professional"   │ Risk: More bugs    │
│ ⭐ RECOMMENDED ⭐                                                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   TIER 3: SHIP THIS MONTH                       │
├─────────────────────────────────────────────────────────────────┤
│ Files: ~12     │ Patterns: 4              │ Providers: 4       │
│ LOC: ~3000     │ Duration: 8-10 days      │ Status: release    │
│ Ship: in 2wks  │ Signal: "Complete"      │ Risk: Over-eng.    │
└─────────────────────────────────────────────────────────────────┘
```

---

## TIER 1 File Checklist (Friday)

```
□ src/executionkit/
  □ __init__.py          (consensus + sync wrapper + exports)
  □ _core.py             (provider protocol + consensus + OpenAI)
  □ _errors.py           (4 error classes)

□ tests/
  □ conftest.py          (MockProvider)
  □ test_consensus.py    (80+ lines)

□ examples/
  □ quickstart_consensus.py

□ pyproject.toml         (deps, metadata, build)
□ README.md              (hero example + roadmap)
□ .gitignore             (Python defaults + .env)
□ py.typed               (empty file for PEP 561)
□ CHANGELOG.md           (release notes)
□ LICENSE                (MIT)
```

**Total: 10 files. ~250 LOC core.**

---

## TIER 2 File Checklist (Wednesday)

```
□ TIER 1 files (above)

□ New/modified:
  □ src/executionkit/
    □ provider.py        (protocols, LLMResponse, ToolCall)
    □ types.py           (PatternResult, TokenUsage, Tool)
    □ _core.py           (refactored: checked_complete, helpers)

  □ patterns.py          (or patterns/ dir with 4 files)
    □ consensus.py       (with PatternResult return)
    □ refine_loop.py
    □ tree_of_thought.py
    □ react_loop.py

  □ src/executionkit/providers/
    □ __init__.py        (lazy imports)
    □ _openai.py
    □ _ollama.py

  □ tests/
    □ test_refine_loop.py
    □ test_tree_of_thought.py
    □ test_react_loop.py
    □ test_providers.py

  □ examples/
    □ quickstart_openai.py
    □ quickstart_ollama.py
    □ (3 more: consensus, refine, tree)
```

**Total: ~7 core files. ~1700 LOC.**

---

## The MVP API (Code Shape)

### TIER 1 (Consensus Only)

```python
from executionkit import consensus, OpenAIProvider

provider = OpenAIProvider("gpt-4o-mini")
result, cost = await consensus(provider, prompt, num_samples=5)
```

### TIER 2 (All Patterns)

```python
from executionkit import consensus, refine_loop, tree_of_thought, react_loop
from executionkit import OpenAIProvider, OllamaProvider

provider = OpenAIProvider("gpt-4o-mini")  # or OllamaProvider("mistral")

# All return PatternResult[T]
result = await consensus(provider, prompt)
result = await refine_loop(provider, prompt)
result = await tree_of_thought(provider, prompt)
result = await react_loop(provider, prompt, tools=[...])

# Access results
print(result.value)      # The answer
print(result.cost)       # TokenUsage
print(result.score)      # Confidence (if computed)
print(result.metadata)   # Extra data (agreement_ratio, etc.)
```

### TIER 3 (With Composition)

```python
from executionkit import pipe, consensus, refine_loop
from executionkit import AnthropicProvider

provider = AnthropicProvider("claude-3-5-sonnet")

# Chain patterns with budget tracking
result = await pipe(
    provider,
    prompt,
    consensus,     # Sample N times, vote
    refine_loop,   # Refine the best answer
    max_budget=TokenUsage(500_000, 200_000),
)

print(result.cost)  # Total cost across BOTH patterns
```

---

## Decision Tree (30 seconds)

```
START HERE
  │
  ├─ "I want feedback in 48 hours"?
  │  └─ YES → TIER 1 (Friday)
  │
  ├─ "All 4 patterns are must-haves"?
  │  └─ YES → TIER 2 (Wednesday) ⭐
  │
  ├─ "Anthropic is required v0.1"?
  │  └─ YES → TIER 3 (2 weeks)
  │
  ├─ "I have <3 days"?
  │  └─ YES → TIER 1 (Friday)
  │
  └─ Otherwise → TIER 2 (Wednesday) ⭐
```

---

## Verification Checklist (All Tiers)

```bash
# Code quality
□ ruff check . && ruff format . --check
□ mypy --strict src/

# Tests
□ pytest --cov-fail-under=80 -m "not integration"

# Real-world smoke test
□ OPENAI_API_KEY=sk-... python examples/quickstart_consensus.py

# Jupyter
□ Test consensus_sync() works in notebook without `nest_asyncio`

# Security
□ Zero hardcoded secrets
□ .env in .gitignore
□ No API keys in examples
```

---

## Key Cuts from Original Plan

| What | TIER 1 | TIER 2 | TIER 3 | Why |
|------|--------|--------|--------|-----|
| TraceEntry | ❌ | ❌ | ✅ v0.2 | Observability |
| ConvergenceDetector | ❌ | ❌ | ✅ v0.2 | Complex, not needed |
| Anthropic | ❌ | ❌ | ✅ | Message conversion tax |
| pipe() | ❌ | ❌ | ✅ | Composition deferred |
| VotingStrategy enum | ❌ | ❌ | ✅ | Default "majority" only |
| RetryConfig | ❌ | ✅ v0.2 | ✅ v0.2 | Use tenacity |

**Result: Plan was 30% over-engineered. We cut ~800 LOC.**

---

## Effort Summary

| Phase | Duration | Effort | Status |
|-------|----------|--------|--------|
| TIER 1 | 4 hours | 1 person | v0.1.0-alpha (Friday) |
| +TIER 2 | +3-4 days | +1-2 people | v0.1.0-beta (Weds) |
| +TIER 3 | +5-6 days | +1-2 people | v0.1.0 (2 weeks) |

---

## Documentation You Need

1. **MVP_TIERS.md** — Full breakdown (copy-paste reference)
2. **SHIP_DECISION.md** — Risk analysis (read before deciding)
3. **TIER1_SCAFFOLD.md** — Exact code (copy-paste if shipping TIER 1)
4. **QUICK_REFERENCE.md** — This file (tape it up)

---

## The Recommended Path

```
TODAY (Fri)
  └─ Decision: Commit to TIER 2
     └─ Tell your team "we ship Wednesday"

FRIDAY EVE
  └─ Cut TIER 1 foundation (4 hours)
     - Scaffold, consensus, OpenAI provider
     - Basic tests, README

MONDAY
  └─ Add 3 more patterns (TIER 2)
     - refine_loop, tree_of_thought, react_loop
     - Heavy testing

TUESDAY
  └─ Add Ollama provider + examples
     - smoke test all 4 patterns × 2 providers

WEDNESDAY
  └─ Final verification + ship
     - ruff, mypy, pytest all green
     - Tag v0.1.0-beta
     - Push to PyPI
     - Announce

NEXT 3 WEEKS
  └─ Collect feedback
     └─ If Anthropic demand exists → ship v0.2 with TIER 3 pieces
     └─ If not → stay lean, iterate on patterns
```

---

## When to Use Each Document

| Document | When | Why |
|----------|------|-----|
| **MVP_SUMMARY.md** | First (this one) | Understand the landscape |
| **MVP_TIERS.md** | Before deciding | See full technical details |
| **SHIP_DECISION.md** | Before deciding | Understand risks & timelines |
| **TIER1_SCAFFOLD.md** | If shipping TIER 1 | Copy-paste exact code |
| **QUICK_REFERENCE.md** | Anytime (this) | 30-second lookup |

---

## Cutting Room Floor (Iteration 1 Casualties)

Things we said NO to so you could ship faster:

- ❌ TraceEntry (observability)
- ❌ ProgressCallback (requires tracing)
- ❌ ConvergenceDetector (use max_iterations)
- ❌ json_extraction (band-aid)
- ❌ Anthropic (too complex for v0.1)
- ❌ Message conversion (250 LOC edge cases)
- ❌ Streaming (nice-to-have)
- ❌ OpenTelemetry (enterprise feature)
- ❌ pipe() (prove patterns first)

**These all come back in v0.2 when you have real demand signal.**

---

## Your Ship Message (Pick One)

### TIER 1
> ExecutionKit v0.1.0-alpha: Consensus voting with cost tracking. OpenAI support. More patterns coming. Try it, break it, tell us what's missing.

### TIER 2 ⭐
> ExecutionKit v0.1.0-beta: Four production-ready reasoning patterns (consensus, refinement, tree-of-thought, react-loop). OpenAI + Ollama support. Test coverage 80%+.

### TIER 3
> ExecutionKit v0.1.0: Composable LLM reasoning library. Four patterns, four providers, pipe() composition, full documentation. Production-ready beta.

---

## Last Minute Questions

**Q: Can I ship TIER 1 Friday and TIER 2 Wednesday?**
A: Yes. That's the hybrid path. Ship TIER 1, get 48h of feedback, iterate, ship TIER 2.

**Q: Do I need Anthropic in v0.1?**
A: No. OpenAI + Ollama prove the design. Ship Anthropic in v0.2.

**Q: Can I skip pytest and ship?**
A: No. Minimum 80% coverage. Non-negotiable.

**Q: What if I run out of time?**
A: Ship TIER 1 Friday. It's done, tested, proven. Iterate from there.

**Q: What's the riskiest part?**
A: Message conversion (TIER 3 only). Everything else is straightforward.

---

## Go/No-Go Decision

**You are GO for:**
- ✅ TIER 1 (Friday EOD)
- ✅ TIER 2 (Wednesday EOD)
- ✅ TIER 3 (2 weeks out)

**Pick one. Start Monday. You've got this.**

---

*Final reminder: All exact code is in `TIER1_SCAFFOLD.md`. All decision criteria are in `SHIP_DECISION.md`. All technical details are in `MVP_TIERS.md`. Go read those. Come back when you decide.*
