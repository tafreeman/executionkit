# ALL ITERATIONS COMPLETE — Final Verdict

## 3 Iterations × 3 Agents = 9 Reviews Synthesized

| Iteration | Market (opus) | Technical (sonnet) | Scope (haiku) |
|-----------|--------------|-------------------|--------------|
| 1 | 4 patterns rated. react_loop THREATENED. DSPy is main competitor. Composability is moat. | 5 blockers, 7 mypy failures, 3 logic bugs, phantom file path. | Cut TraceEntry, ProgressCallback, Anthropic, ConvergenceDetector, json_extraction, error hierarchy. |
| 2 | DSPy deep dive: BestOfN != consensus, Refine has no convergence. ConvergenceDetector IS differentiator. Voting pre-adoption. Google Cascades dead. | 4 of 8 cuts UNSAFE: ConvergenceDetector, json_extraction, error hierarchy, VotingStrategy. Corrected. | 3 tiers defined. Tier 2 recommended (~1,700 LOC, this week). |
| 3 | 12-month survival YES. pipe() is real moat. ToT deferred (academic). Market narrow but real (DSPy's 23K stars prove Camp 2 exists). 90-day kill condition. | All 5 blockers have exact fixes (3-15 LOC each). All 7 mypy failures resolved. READY TO BUILD. | Final IN/OUT locked. 3 patterns + pipe() + 2 providers. |

## Convergence Across Iterations

### Items that SURVIVED all 3 iterations (high confidence)
- consensus pattern (strongest moat, no PyPI competitor)
- refine_loop with ConvergenceDetector (differentiator vs DSPy)
- OpenAI + Ollama providers
- RetryConfig + gather_resilient/gather_strict
- TokenUsage + CostTracker + checked_complete
- agreement_ratio in consensus metadata
- VotingStrategy enum (MAJORITY + UNANIMOUS)
- NaN score validation
- CancelledError guards
- json_extraction.py (Ollama fallback)

### Items KILLED across iterations (high confidence CUT)
- Anthropic provider + _conversion.py (deferred v0.2)
- tree_of_thought (deferred v0.2 — academic, most complex)
- TraceEntry + ProgressCallback + request_id (observability v0.2)
- StreamingProvider implementation (v0.2)
- max_trace_entries parameter
- started_at + per-call usage fields
- mkdocs documentation site
- ruff D docstring enforcement
- 10 examples → 5

### Items that FLIP-FLOPPED (resolved)
| Item | Iter 1 | Iter 2 | Iter 3 (Final) | Resolution |
|------|--------|--------|----------------|------------|
| ConvergenceDetector | CUT | KEEP | **IN** | Differentiator vs DSPy. Wastes 8 LLM calls if cut. |
| json_extraction.py | CUT | KEEP | **IN** | Ollama fallback needed. Unsafe to cut. |
| pipe() | CUT | KEEP | **IN** | Cross-pattern budget tracking is the moat. |
| Kit session | CUT | — | **IN** | Needed for multi-pattern workflows. |
| react_loop | — | THREATENED | **IN** | Composition via pipe() is the differentiator. |
| Error hierarchy | CUT to 4 | CUT to 5 | **9 classes** | PermanentError prevents auth retry loops. |
| VotingStrategy | CUT enum | KEEP enum | **IN** (2 values) | String accepts invalid values silently. |
| Default max_cost | — | Optional, no default | **OUT** (with ToT) | Deferred with tree_of_thought. |

## Final v0.1 Specification

### What Ships
- **3 patterns**: consensus, refine_loop, react_loop
- **1 compositor**: pipe()
- **1 session**: Kit
- **2 providers**: OpenAI, Ollama, Mock
- **4 engine modules**: retry, parallel, convergence, json_extraction
- **9 error classes**, **7 types**, **1 cost tracker**
- **5 examples**, CLI, README, CONTRIBUTING.md
- ~1,700 LOC, 7-8 days to build

### What Defers to v0.2
- tree_of_thought (beam search)
- Anthropic provider + message converter
- TraceEntry + ProgressCallback (observability)
- StreamingProvider
- OpenTelemetry
- mkdocs site

### Pre-Build Checklist (Day 1 morning)
- [ ] Fix LLMChunk stub (3 lines)
- [ ] Fix _subtract() in compose.py (5 lines)
- [ ] Add UnsupportedContentError (1 line)
- [ ] Write full RetryConfig class (15 lines)
- [ ] Add empty-steps guard to pipe() (2 lines)
- [ ] Add TypeAlias to Evaluator (1 line)
- [ ] Fix ToolCallingProvider signature (keep parent kwargs)
- [ ] Add T = TypeVar("T") to retry.py
- [ ] Add max_retries=0 guard to with_retry
- [ ] Correct pyproject.toml source file path (tools/llm/ not agentic_v2/tools/llm/)

## VERDICT: GO

Build Tier 2. Ship in 7-8 days. Set 90-day kill condition: <50 GitHub stars and zero production evidence → archive.
