# Review Audit: Issue → Resolution Traceability

Every issue raised across 6 rounds, mapped to its resolution status in PLAN.md.

## Round 5: Antagonistic Reviews

### Market Antagonist (KILL 78%)

| # | Issue | Severity | Resolution in PLAN.md | Status |
|---|-------|----------|----------------------|--------|
| M1 | Target personas choose alternatives in practice | 7/10 | Not addressed — market risk acknowledged but not mitigated in plan | OPEN |
| M2 | Quickstart doesn't beat raw SDK ("2+2" example) | 8/10 | Hero example changed to pipe(refine_loop, consensus) on contract analysis (line 694-713) | RESOLVED |
| M3 | Zero competitive moat — LangGraph/DSPy can absorb | 9/10 | Not addressed — structural market risk, mitigated only by speed-to-ship | OPEN (accepted risk) |
| M4 | Repeats failure patterns of Guidance, Marvin, PromptTools | 8/10 | Not addressed — acknowledged as market context, not actionable in code plan | OPEN (accepted risk) |
| M5 | Maintenance sustainability (~48 hrs/year for 4 providers) | 5/10 | Partially addressed — each provider is ~60-120 LOC thin wrapper (line 592), lazy imports | PARTIAL |
| M6 | "itertools" tagline is a liability | — | Tagline changed to "Reliable LLM calls through voting, refinement, and search" (line 1, 97) | RESOLVED |

### Technical Antagonist (BLOCK)

| # | Issue | Severity | Resolution in PLAN.md | Status |
|---|-------|----------|----------------------|--------|
| T1 | dict[str, Any] messages push all errors to runtime | 7/10 | Not addressed — plan acknowledges this is a tradeoff, stays with loose dicts for cross-provider compat | OPEN (accepted tradeoff) |
| T2 | TaskGroup cancellation destroys partial ToT results | 8/10 | gather_resilient uses return_exceptions=True (line 329-342). ToT uses gather_resilient, failed evals score 0.0 (line 506) | RESOLVED |
| T3 | No default cost budget; depth-granular guard lets overshoot | 9/10 | Default max_cost on ToT: TokenUsage(500K, 200K, 100 calls) (line 499). Per-call check via checked_complete (line 428) | RESOLVED |
| T4 | Anthropic message history conversion is 150+ LOC, not thin wrapper | 8/10 | _conversion.py moved to providers/, 200-250 LOC estimate, 9 edge cases listed (line 575-590) | RESOLVED |
| T5a | NaN evaluator scores silently corrupt results | 7/10 | validate_score raises ValueError on NaN/out-of-range (line 412-416). ConvergenceDetector validates (line 396) | RESOLVED |
| T5b | Tool.execute hangs forever (no timeout) | 7/10 | Tool.timeout=30.0 default (line 309). react_loop wraps in asyncio.wait_for (line 527) | RESOLVED |
| T5c | Consensus with zero agreement returns random result silently | 7/10 | agreement_ratio in metadata (line 547). ConsensusFailedError for UNANIMOUS (line 547) | PARTIAL — MAJORITY still returns arbitrary winner on tie |
| T5d | finish_reason="length" not checked | 7/10 | was_truncated property on LLMResponse (line 232-233) | PARTIAL — property exists but patterns don't auto-retry on truncation |
| T6 | MockProvider tests structure, not behavioral quality | 6/10 | Not addressed — plan still has no benchmark suite or quality regression tests | OPEN |
| T7 | response_format generics won't type-check (need @overload) | 7/10 | Not addressed — no @overload decorators mentioned for patterns that accept response_format | OPEN |

### API Design Antagonist (REJECT)

| # | Issue | Severity | Resolution in PLAN.md | Status |
|---|-------|----------|----------------------|--------|
| A1 | react_loop name collision with React.js | 6/10 | Not addressed — name kept as react_loop | OPEN |
| A2 | No session/client pattern — provider repeated everywhere | 8/10 | Kit session class added (kit.py referenced in line 33, structure shown in R5 plan) | RESOLVED — but Kit code not shown in current PLAN.md |
| A3 | PatternResult .value ceremony on every call | 7/10 | __str__ returns str(self.value) (line 296-297). __iter__ yields value, cost (line 299-301) | RESOLVED |
| A4 | Composition broken — "itertools" tagline is a lie | 9/10 | pipe() ships in v0.1 (line 444-480). Budget-aware. Partial cost preservation. | RESOLVED |
| A5 | asyncio.run() sync wrappers break in Jupyter | 7/10 | Jupyter-safe sync wrappers mentioned (line 29, 664) | PARTIAL — implementation not shown in plan (no nest_asyncio code) |
| A6 | _engine/ private but custom patterns need it | 8/10 | Renamed to engine/ (PUBLIC) (line 43). patterns/base.py public (line 38, 407-438) | RESOLVED |
| A7 | CostMetrics name misleading (no dollar costs) | — | Renamed to TokenUsage (line 265-270) | RESOLVED |
| A8 | No stability guarantee / migration path | 5/10 | Stability policy section added (line 684-690) | RESOLVED |

## Round 6: Expert Reviews

### Senior Architect (NEEDS WORK)

| # | Issue | Resolution in PLAN.md | Status |
|---|-------|----------------------|--------|
| AR1 | LLMProvider conflates completion + tool calling + streaming; hasattr bad | ToolCallingProvider + StreamingProvider extension Protocols defined (line 186-205) | RESOLVED |
| AR2 | _checked_complete is private but custom patterns need it | Renamed to checked_complete, moved to public patterns/base.py (line 407-438) | RESOLVED |
| AR3 | message_converter.py is provider-specific, doesn't belong in engine/ | Moved to providers/_conversion.py (line 55, 575) | RESOLVED |
| AR4 | pipe() doesn't enforce budget across steps; CostTracker undefined | pipe() budget-aware with _subtract (line 462). But CostTracker class still not defined in plan | PARTIAL — CostTracker referenced at line 423 but never defined |
| AR5 | Error hierarchy mixes provider and pattern errors | Split into LLMError + PatternError branches under ExecutionKitError (line 235-253) | RESOLVED |
| AR6 | tool_calls as list[dict] is untyped sprawl | ToolCall dataclass defined (line 208-213). LLMResponse uses list[ToolCall] (line 218) | RESOLVED |
| AR7 | ExecutionContext is vestigial — either give it a purpose or cut it | Scoped to pipe() shared state only (line 401-403). If no consumer, cut. | PARTIAL — hedging ("if no consumer, cut") not a decision |
| AR8 | pipe() callable signature not enforced | PatternStep Protocol added (line 317-319). pipe() uses *steps: PatternStep (line 448) | RESOLVED |
| AR9 | TruncatedResponseError is dead code | Not addressed — still in error hierarchy implicitly | OPEN — actually was removed from the hierarchy at line 235-253 |

### Senior Engineer (NEEDS REFINEMENT)

| # | Issue | Resolution in PLAN.md | Status |
|---|-------|----------------------|--------|
| EN1 | gather_resilient doesn't handle CancelledError (leaks through return_exceptions) | Explicit try/except CancelledError: raise (line 341-342) | RESOLVED |
| EN2 | with_retry might retry on CancelledError | CancelledError guard added (line 375-376) | RESOLVED |
| EN3 | gather_strict callers get raw ExceptionGroup | ExceptionGroup unwrap for single exceptions (line 358-362) | RESOLVED |
| EN4 | Message converter underscoped; 9 edge cases listed | All 9 edge cases listed as requirements (line 579-589). 200-250 LOC estimate (line 590) | RESOLVED |
| EN5 | pipe() loses partial costs on cancellation | try/except preserves partial PatternResult (line 467-474) | RESOLVED |
| EN6 | No request_id or timing on TraceEntry | request_id (UUID4), started_at (monotonic), duration_ms added (line 282-284, 602-614) | RESOLVED |
| EN7 | No per-call token usage in trace | usage dict added to TraceEntry (line 284) | RESOLVED |
| EN8 | Temperature defaults are OpenAI-optimized; Ollama users will get garbage | Documentation note added (line 596-598) | RESOLVED |
| EN9 | max_concurrency not exposed on tree_of_thought | max_concurrency param added to ToT signature (line 500) | RESOLVED |
| EN10 | patience=2 too aggressive (premature termination) | Default increased to 3 (line 392, 559) | RESOLVED |
| EN11 | _checked_complete budget check can overshoot by one call's worth of tokens | Not addressed — budget checked BEFORE call but response tokens not pre-counted | OPEN |
| EN12 | No max_trace_entries config for memory bound | Not addressed — trace grows unboundedly | OPEN |
| EN13 | Kit ambiguous: is max_cost per-call or cumulative? | Not addressed — plan doesn't specify | OPEN |
| EN14 | Missing specific test cases (semaphore release, Kit propagation, multi-tool round-trip, pipe cost on failure) | test_concurrency.py listed (line 69). Other specific tests not enumerated in plan. | PARTIAL |

### OSS Expert (NEEDS POLISH)

| # | Issue | Resolution in PLAN.md | Status |
|---|-------|----------------------|--------|
| OS1 | Hero example ("2+2") doesn't excite | Changed to pipe(refine_loop, consensus) on contract analysis (line 694-713) | RESOLVED |
| OS2 | No CLI entry point | __main__.py added: executionkit check/demo/version (line 30, 665) | RESOLVED |
| OS3 | Missing PyPI metadata (keywords, classifiers, URLs, license) | Full metadata in pyproject.toml (line 93-137) | RESOLVED |
| OS4 | No docstring standard | Google-style enforced via ruff D rules (line 155-157) | RESOLVED |
| OS5 | No docs site | mkdocs-material in Phase 3 (line 81-86, 673) | RESOLVED |
| OS6 | Examples insufficient; wrong quickstart | 10 examples (line 71-80). quickstart_openai.py replaces quickstart_github.py | RESOLVED |
| OS7 | No CONTRIBUTING.md | Added to Phase 3 (line 26, 671) | RESOLVED — but content not specified |
| OS8 | No CHANGELOG.md | Added to project root (line 24) | RESOLVED |
| OS9 | "Composable LLM reasoning patterns" tagline weak | Changed to "Reliable LLM calls through voting, refinement, and search" (line 97) | RESOLVED |
| OS10 | Python 3.11+ requirement aggressive; justification needed | Not addressed in plan — no justification for excluding 3.10 | OPEN |
| OS11 | Kit.py code/implementation not shown | Kit referenced but full code sketch not in current plan revision | OPEN |
| OS12 | Sync wrapper implementation not shown (nest_asyncio) | Mentioned but code not shown in plan | OPEN |
| OS13 | CONTRIBUTING.md content not specified (provider template, pattern template) | CONTRIBUTING.md listed but no content described | OPEN |

---

## Summary: OPEN Items Requiring Resolution

### MUST ADDRESS (affects correctness or adoption)

| # | Source | Issue | Recommended Resolution |
|---|--------|-------|----------------------|
| 1 | AR4 | CostTracker class referenced but never defined | Add CostTracker definition to cost.py section. Mutable accumulator with record(response) and total_tokens property. |
| 2 | AR7 | ExecutionContext purpose is hedging ("if no consumer, cut") | Make a decision: CUT it from v0.1. pipe() uses a simple dict or TokenUsage accumulator, not a full context object. |
| 3 | EN11 | Budget check can overshoot by one call's worth of tokens | Document this as known behavior. Budget is "soft cap" — actual usage may exceed by up to max_tokens. |
| 4 | EN13 | Kit.max_cost: per-call or cumulative? | Decide: PER-CALL. Each kit.consensus() gets its own budget. Document this. |
| 5 | OS11 | Kit session class code not shown in plan | Add Kit code sketch to plan. |
| 6 | OS12 | Jupyter sync wrapper implementation not shown | Add _run_sync code sketch with nest_asyncio detection. |
| 7 | T7 | response_format generics need @overload for mypy --strict | Add @overload note for consensus() — one overload with response_format: type[T] returning PatternResult[T], one without returning PatternResult[str]. |

### SHOULD ADDRESS (improves quality)

| # | Source | Issue | Recommended Resolution |
|---|--------|-------|----------------------|
| 8 | T5c | MAJORITY consensus on tie returns arbitrary winner | Document: "On tie, first-encountered response wins (deterministic per-run, not guaranteed across runs)." Add tie_count to metadata. |
| 9 | T5d | was_truncated exists but patterns don't auto-retry | Add: patterns log a warning and include truncated=True in PatternResult.metadata. Auto-retry deferred to v0.2. |
| 10 | EN12 | Trace grows unboundedly | Add max_trace_entries: int | None = 1000 param to all patterns. When exceeded, oldest entries dropped. |
| 11 | EN14 | Specific test cases not enumerated | Add test case checklist to Test Strategy section. |
| 12 | OS7/13 | CONTRIBUTING.md content not specified | Add outline: "How to add a provider" (5 steps), "How to add a pattern" (5 steps), "Good first issues" list. |
| 13 | OS10 | Python 3.11+ not justified | Add note: "Requires 3.11+ for asyncio.TaskGroup and ExceptionGroup. 3.10 support would require exceptiongroup backport and manual task management — deferred." |

### ACCEPTED RISKS (market/strategic, not resolvable in code)

| # | Source | Issue | Why Accepted |
|---|--------|-------|-------------|
| M1 | Market | Target personas choose alternatives | Speed-to-ship and composition story are the differentiators. |
| M3 | Market | Zero competitive moat | Correct. This is a bet on execution speed and developer experience. |
| M4 | Market | Repeats graveyard patterns | Acknowledged. Mitigated by keeping scope tiny (4 patterns, not a framework). |
| T1 | Tech | dict[str, Any] messages are untyped | Cross-provider compatibility requires loose types at the Protocol boundary. |
| T6 | Tech | No behavioral quality tests | Deferred — requires real LLM calls and subjective quality metrics. Integration test markers are the hook for future work. |
| A1 | API | react_loop name collision with React.js | React (Reason+Act) is the canonical academic name. Renaming would confuse the ML audience. |
