# ExecutionKit Ship Decision Framework

## The Core Trade-off

**TIER 1 (Tomorrow)** = Minimum viable proof of concept
- Single pattern (consensus) proves unified cost tracking works
- One provider (OpenAI) avoids conversion complexity
- ~250 LOC of working, tested code
- Signal: "We can ship, we understand the problem space"
- Risk: Too minimal to validate real-world usage patterns

**TIER 2 (This Week)** = Launch-ready feature set
- All 4 patterns validated as standalone tools
- 2 providers (OpenAI + Ollama) show provider-agnostic design
- ~1700 LOC, higher code quality bar
- Signal: "This is production-quality for pattern orchestration"
- Risk: More bugs, more surface area to test before release

**TIER 3 (This Month)** = Full-featured beta
- Anthropic support validates cross-provider compatibility
- pipe() composition proves the genuine moat
- Message conversion edge cases handled
- Complete documentation and 10 examples
- Signal: "We built the right abstraction"
- Risk: Anthropic conversion complexity, over-engineering trap

---

## Go/No-Go Criteria

### SHIP TIER 1 IF...
- You want to validate market fit quickly (this week feedback)
- You're comfortable being wrong about which patterns matter
- You want to iterate on API design based on real users
- Your team is small (<3 people) and velocity matters
- You can handle the PR narrative: "Proof of concept, more coming"

### SHIP TIER 2 IF...
- You want to be "real v0.1" on day one
- You have 1-2 weeks before public announcement
- Pattern stability is worth the extra testing burden
- You're comfortable with 2+ providers from day one
- You want strong signal: "All our core patterns work"

### SHIP TIER 3 IF...
- You have 3+ weeks to mature the code
- Anthropic is a strategic priority (enterprise deals?)
- Message conversion edge cases feel manageable
- You want pipe() composability from day one
- You can justify 3000+ LOC maintenance burden

---

## Timeline Reality Check

### TIER 1 Timeline

```
Day 1 (Friday)
├─ Scaffold: pyproject.toml, provider protocol, LLMResponse, consensus pattern
├─ Implement: OpenAI provider, 50 lines
├─ Test: Unit + integration, 150 lines
├─ Polish: README, docstrings, ruff + mypy
└─ Ship: Tag v0.1.0-alpha on PyPI

Total effort: 1 developer × 1 day
Launch: Friday EOD
```

### TIER 2 Timeline

```
Day 1 (Friday) — TIER 1 foundation
Day 2 (Monday)
├─ Refactor consensus to return PatternResult
├─ Implement refine_loop (150 LOC)
├─ Implement tree_of_thought (200 LOC)
├─ Write tests: 250 LOC
└─ All providers working

Day 3 (Tuesday)
├─ Implement react_loop (200 LOC)
├─ Ollama provider (100 LOC)
├─ Full test suite: 150 LOC
└─ Verification: all 4 patterns × 2 providers (smoke test)

Day 4 (Wednesday)
├─ Final ruff + mypy + pytest
├─ README expansion
├─ 5 examples (100 LOC each)
└─ Ship: Tag v0.1.0-beta on PyPI

Total effort: 1-2 developers × 3-4 days
Launch: Wednesday EOD
Gap from TIER 1: +3 days
```

### TIER 3 Timeline

```
Days 1-4: TIER 2 foundation
Days 5-7 (Thursday-Monday)
├─ Anthropic provider (120 LOC)
├─ Message conversion (250 LOC, hardest part)
├─ Round-trip tests on 9 edge cases (300 LOC)
├─ pipe() composition (80 LOC)
├─ Kit session object (50 LOC)
└─ Integration tests: full 16-combo matrix (200 LOC)

Days 8-10 (Tuesday-Thursday)
├─ Complete documentation: mkdocs setup (300 LOC)
├─ 10 examples (500 LOC)
├─ CONTRIBUTING guide
├─ Full coverage audit
└─ Ship: Tag v0.1.0 on PyPI

Total effort: 2 developers × 8-10 days
Launch: Thursday (2.5 weeks out)
Gap from TIER 2: +5 days
```

---

## Risk Assessment

### TIER 1 Risks

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| API design needs rework | HIGH | Ship early, iterate on v0.1.1. Lock only consensus function signature. |
| Missing one critical pattern | MEDIUM | Customer feedback will tell you. Add in v0.2. |
| OpenAI-only feels incomplete | MEDIUM | Ollama example in TIER 2 shows it's coming. |
| Coverage gaps in consensus | LOW | Consensus voting is simple. One pattern = more test depth. |
| No message conversion | LOW | Say "v0.2" clearly. Customers don't expect Anthropic yet. |

### TIER 2 Risks

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| tree_of_thought evaluation logic wrong | MEDIUM | Heavy unit testing. Default evaluator is simple (0-10 LLM score). |
| react_loop tool timeout edge case | MEDIUM | Test tool hangs, cancellation, partial results. |
| refine_loop convergence detection wrong | MEDIUM | Start with simple max_iterations. Add convergence in v0.2. |
| Ollama integration broken | LOW | Ollama is simple (stdlib HTTP). Test locally. |
| Coverage gaps across 4 patterns | MEDIUM | Target 80% minimum. Ship with known gaps documented. |

### TIER 3 Risks

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| Message conversion edge cases | MEDIUM-HIGH | 9 documented cases. Round-trip testing. Anthropic team review. |
| pipe() budget math wrong | MEDIUM | Heavy integration testing. Test all 4 patterns in sequence. |
| Over-engineering for v0.1 | HIGH | You feel this already. Stick to TIER 2 unless Anthropic is mandatory. |
| Documentation debt | MEDIUM | Docs-as-code: docstrings → mkdocs. Automate as much as possible. |
| Maintenance burden grows faster | HIGH | 3000 LOC = more bugs = slower iteration. Okay if 3-person team. |

---

## Market Signal Comparison

### What Users Hear

**TIER 1 Ship Message:**
> "ExecutionKit: Composable LLM reasoning patterns. v0.1.0-alpha. Consensus voting works, message cost tracking works. More patterns coming. Try it, break it, tell us what's missing."

**Signal sent:** Scrappy, fast-moving, open to feedback. Risk: Feels incomplete.

**TIER 2 Ship Message:**
> "ExecutionKit: Four production-ready reasoning patterns (consensus, refinement, tree-of-thought, react-loop) with unified cost tracking. OpenAI + Ollama support. Full test coverage. v0.1.0-beta. Getting ready for 1.0."

**Signal sent:** Professional, feature-complete, thoughtful design. Risk: Might be over-scoped.

**TIER 3 Ship Message:**
> "ExecutionKit: Composable LLM reasoning library. Consensus, refinement, tree-of-thought, react-loop. Works with OpenAI, Anthropic, Ollama, custom providers. Pipe patterns together with budget tracking. v0.1.0. Production-ready beta."

**Signal sent:** Comprehensive, well-designed, ready for enterprise. Risk: Looks like you over-engineered.

---

## Personal Recommendation

### Choose TIER 2

**Why:**

1. **Sweet spot of risk/reward.** You get all 4 patterns (validated in the plan), 2 providers (proves provider-agnostic design), and 3-4 days of work vs. 1 day (TIER 1) or 8-10 days (TIER 3).

2. **Ship message is clear.** "Four patterns that actually work, two providers to prove it" is way more compelling than "one consensus pattern" but way more believable than "comprehensive library with Anthropic."

3. **No message conversion complexity.** TIER 3's biggest risk is Anthropic edge cases. Skip it. TIER 2 says "more providers coming" and you deliver in v0.2 without the stress.

4. **Anthropic can be v0.2.** Customers won't be surprised. "We shipped OpenAI + Ollama in v0.1, Anthropic + custom providers in v0.2" is a totally credible roadmap.

5. **pipe() can wait.** Composition is the "genuine moat," but customers need to trust individual patterns first. Prove the 4 patterns work standalone, THEN add composition.

6. **Testing burden is fair.** 80% coverage across 4 patterns is achievable. 16-combo provider matrix is testable but not worth v0.1 if Anthropic isn't in it.

**Ship TIER 2 on Wednesday. Collect feedback. Ship v0.2 (Anthropic + pipe() + tracing) in 3-4 weeks based on what users actually ask for.**

---

## Alternative Path: TIER 1 → TIER 2 Hybrid

If you're genuinely unsure about pattern demand:

1. **Ship TIER 1 Friday morning** (4 hours max)
2. **Collect 48 hours of feedback** (Discord, Twitter, email)
3. **Decision point Monday:** Do you hear "gimme more patterns" or "this API doesn't work for me"?
   - If patterns are loved: ship TIER 2 Wednesday
   - If API feedback is critical: iterate on TIER 1, rethink TIER 2

**This delays final ship by 3 days but removes 1 week of estimation risk.**

---

## Acceptance Criteria by Tier

### TIER 1 Acceptance Checklist
- [ ] consensus() returns (value, cost) tuples
- [ ] OpenAIProvider works
- [ ] ruff + mypy + pytest 80% all pass
- [ ] examples/quickstart_consensus.py runs end-to-end
- [ ] Zero hardcoded secrets
- [ ] README has hero example + "coming soon" roadmap

### TIER 2 Acceptance Checklist
- [ ] All of TIER 1
- [ ] 4 patterns (consensus, refine, tree-of-thought, react-loop) return PatternResult[str]
- [ ] 2 providers (OpenAI, Ollama) work with all 4 patterns
- [ ] Each pattern has ≥3 tests (unit, edge case, integration)
- [ ] Agreement_ratio and other metadata computed correctly
- [ ] Tool timeouts work in react_loop
- [ ] 5 examples (quickstart, consensus, refine, tree_of_thought, react_loop)

### TIER 3 Acceptance Checklist
- [ ] All of TIER 2
- [ ] Anthropic provider with round-trip message conversion (9 edge cases)
- [ ] pipe() composes patterns with shared budget tracking
- [ ] Complete mkdocs documentation
- [ ] 10 examples including pipe() and composition
- [ ] CONTRIBUTING guide for custom providers and patterns

---

## If You Ship TIER 1, What's Your Day 2?

```
Immediately after ship:
1. Monitor: Discord, HN, Twitter, issues for API feedback
2. Collect: DM 10 users asking "what would make this useful?"
3. Iterate: v0.1.1 hotfixes (usually API tweaks, rare bugs)
4. Decision: By Monday, decide TIER 2 or pivot

If TIER 2 is go:
5. Parallelize: 2 people on patterns, 1 on providers
6. Integration test aggressively
7. Ship Wednesday (3 days later)

If pivot is needed:
5. Redesign API based on feedback
6. Ship v0.2 with new direction
```

---

## Final Decision Framework

**If you answer "YES" to any of these:**
- "I want to ship tomorrow" → TIER 1
- "I'm not sure which patterns matter" → TIER 1
- "I want customer feedback before Anthropic" → TIER 1

**If you answer "YES" to any of these:**
- "I want to be taken seriously as a v0.1" → TIER 2
- "All 4 patterns are must-haves" → TIER 2
- "I have 3-4 days to build" → TIER 2
- "Ollama + OpenAI is enough for launch" → TIER 2

**If you answer "YES" to ANY of these:**
- "Anthropic is required for v0.1" → TIER 3
- "pipe() composability is the main story" → TIER 3
- "I want complete documentation on day one" → TIER 3
- "3000+ LOC and 2+ weeks is fine" → TIER 3

**Otherwise: TIER 2.**

---

## Recommendation Summary

**Ship TIER 2.** It's the professional middle ground. All 4 core patterns, proof of provider-agnostic design, same-day launch by Wednesday. Defers Anthropic and composition to v0.2 based on actual demand.

Good luck.
