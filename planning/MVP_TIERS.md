# ExecutionKit MVP Tiers — Ship-Ready Scope Definition

**Question:** What is the absolute smallest thing you could ship that proves the concept?

**Answer:** TIER 1 is a working consensus pattern + OpenAI provider in ONE file, tested, shipped as v0.1.0-alpha.

---

## TIER 1: Ship Tomorrow (1-2 patterns, <500 LOC, 1 file core)

### Philosophy
Single, shippable artifact that proves "composable patterns + provider-agnostic API = value."
- No tracing, no progress callbacks, no retry logic (document "wrap with tenacity if needed")
- No type-heavy result objects; patterns return `(value, cost)` tuple
- Consensus only (voting is the clearest proof of concept)
- OpenAI only (one provider, zero conversion complexity)
- No separate `CostTracker` class—just accumulate in pattern function

### File Structure (3-4 files)

```
src/executionkit/
  __init__.py              # Public exports (consensus + provider) + sync wrapper
  _core.py                 # Everything else (Provider protocol, LLMResponse, consensus pattern, OpenAI impl)
  _errors.py               # 4 error classes
tests/
  test_consensus.py        # Unit + integration tests
examples/
  quickstart_consensus.py  # Hero example
README.md
pyproject.toml
```

### Type Surface (Minimal)

```python
# provider.py — FROZEN protocol for 0.x
@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self, messages: Sequence[dict[str, Any]], *,
        temperature: float = 0.7, max_tokens: int = 4096, **kwargs: Any,
    ) -> "LLMResponse": ...

# types.py — TINY
@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    usage: dict[str, Any] = field(default_factory=dict)  # {input_tokens, output_tokens}

# No PatternResult — return (value: str, cost: int)
# No TraceEntry, ProgressCallback, VotingStrategy enum, Tool, Evaluator
# No PatternStep protocol, TokenUsage, ConvergenceDetector
```

### Errors (4 only)

```python
class ExecutionKitError(Exception): pass
class LLMError(ExecutionKitError): pass
class RateLimitError(LLMError): pass
class BudgetExhaustedError(ExecutionKitError): pass
```

### Pattern: Consensus (1 only)

```python
async def consensus(
    provider: LLMProvider, prompt: str, *,
    num_samples: int = 5,
    response_format: type[T] | None = None,
    temperature: float = 0.9, max_tokens: int = 4096,
    max_budget_tokens: int = 50_000,  # Soft cap
    max_concurrency: int = 5,
    **kwargs: Any,
) -> tuple[str | T, int]:  # (value, total_tokens_used)
    """Run prompt num_samples times, return most common response + token cost."""

    # Parallel execution with semaphore
    results = await gather_with_limit(
        [provider.complete(messages, ...) for _ in range(num_samples)],
        max_concurrency=max_concurrency
    )

    # Vote: most common string (simple majority)
    value_counts = Counter(r.content for r in results)
    best_value = value_counts.most_common(1)[0][0]

    # Total cost
    total_tokens = sum(r.usage.get("total_tokens", 0) for r in results)

    return best_value, total_tokens
```

### OpenAI Provider (1 only)

```python
class OpenAIProvider:
    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None):
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model

    async def complete(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return LLMResponse(
            content=response.choices[0].message.content or "",
            usage={"input_tokens": response.usage.prompt_tokens,
                   "output_tokens": response.usage.completion_tokens,
                   "total_tokens": response.usage.total_tokens},
        )
```

### Dependencies
- `pydantic` (for BaseModel validation on inputs)
- `openai>=1.0` (optional; runtime error if not installed and OpenAI used)

### Sync Wrapper (Jupyter-safe)

```python
def consensus_sync(provider, prompt, **kwargs):
    return asyncio.run(consensus(provider, prompt, **kwargs))
```

### Test Coverage
- Unit: MockProvider returns fixed responses, test voting logic
- Integration: Real OpenAI call (marked `@pytest.mark.integration`, skipped in CI)
- Edge cases: Tie resolution, all responses same, empty results
- Target: 80% coverage

### Hero Example (examples/quickstart_consensus.py)

```python
from executionkit import consensus
from executionkit.providers import OpenAIProvider

provider = OpenAIProvider("gpt-4o-mini")
prompt = "Is Python easier to learn than Rust? Answer in 1 sentence."

result, cost = await consensus(provider, prompt, num_samples=5)
print(result)  # Most agreed-upon answer
print(f"Cost: {cost} tokens")
```

### README: Minimal
- Install: `pip install executionkit openai`
- What it is: "Composable LLM reasoning patterns with unified cost tracking"
- Consensus example
- Other patterns coming in v0.2
- Stability: "v0.1.0-alpha. API frozen for 0.x. No breaking changes until 1.0."

### Verification Checklist (SHIP GATE)
- [ ] `ruff check` + `ruff format --check` + `mypy --strict` pass
- [ ] `pytest --cov-fail-under=80` passes (no integration tests in CI)
- [ ] `examples/quickstart_consensus.py` works with real API key
- [ ] `examples/quickstart_consensus.py` works in Jupyter (async wrapper tested)
- [ ] Zero hardcoded secrets, `.env` in `.gitignore`
- [ ] README complete, `pyproject.toml` has all metadata

### Estimated LOC
- `_core.py`: 200 (consensus + OpenAI + helpers)
- `_errors.py`: 20
- `__init__.py`: 30
- Tests: 150
- Examples: 50
- **Total Core: ~250 LOC**

### Git Release
- Tag: `v0.1.0-alpha`
- Commit message: `feat: initial release — consensus pattern + OpenAI provider`
- PyPI: `pip install executionkit`

---

## TIER 2: Ship This Week (All essential patterns + 2 providers, ~1200 LOC, ~7 files)

### Philosophy
Add 3 more patterns (tree_of_thought, refine_loop, react_loop) + Ollama provider.
Still minimal infrastructure (no Anthropic, no conversion, no tracing).
Introduce proper `PatternResult` object for consistency.

### File Structure

```
src/executionkit/
  __init__.py              # All exports + sync wrappers
  provider.py              # LLMProvider protocol + ToolCallingProvider + LLMResponse + ToolCall
  types.py                 # PatternResult[T], TokenUsage, Tool, Evaluator, VotingStrategy (enum optional)
  _errors.py               # 6 error classes (add MaxIterationsError, ConsensusFailedError)
  _core.py                 # Helper: checked_complete, validate_score, gather_resilient
  patterns.py              # All 4 patterns in one file OR split into patterns/__init__.py + patterns/each.py
  providers/
    __init__.py            # Lazy imports + helpful errors
    _openai.py             # OpenAI
    _ollama.py             # Ollama (stdlib only, zero deps)
tests/
  test_providers.py
  test_consensus.py
  test_refine_loop.py
  test_tree_of_thought.py
  test_react_loop.py
examples/
  quickstart_openai.py
  quickstart_ollama.py
  consensus_voting.py
  refine_classification.py
```

### Type Surface (Moderate)

```python
# PatternResult — simplified from plan
@dataclass(frozen=True, slots=True)
class PatternResult(Generic[T]):
    value: T
    cost: TokenUsage                    # (input_tokens, output_tokens, llm_calls)
    score: float | None = None          # For patterns that compute confidence
    metadata: dict[str, Any] = field(default_factory=dict)  # agreement_ratio, tie_count, etc.

@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage: ...
    @property
    def total_tokens(self) -> int: return self.input_tokens + self.output_tokens

# Tool for react_loop
@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    execute: Callable[..., Awaitable[str]]
    timeout: float = 30.0

# No TraceEntry, ProgressCallback, PatternStep protocol, ConvergenceDetector
```

### Patterns (4)

1. **consensus** — Parallel voting (from TIER 1, enhanced to return PatternResult with agreement_ratio)
2. **refine_loop** — Generate → evaluate → improve → repeat (simple max_iterations, no convergence detector)
3. **tree_of_thought** — Beam search: branch → evaluate → prune → recurse
4. **react_loop** — Think → act (tool call) → observe (limited to max_rounds, no tool concurrency)

Each pattern signature:

```python
async def pattern_name(
    provider: LLMProvider, prompt: str, *,
    temperature: float = 0.7, max_tokens: int = 4096,
    max_budget_tokens: int | None = None,
    on_error: str = "raise",  # or "warn" to collect and continue
    **kwargs: Any,
) -> PatternResult[str]:
```

### Providers (2)

1. **OpenAIProvider** — from TIER 1
2. **OllamaProvider** — stdlib urllib + asyncio.to_thread (zero dependencies)

### Errors (6)

```python
ExecutionKitError (root)
  ├─ LLMError
  │  ├─ RateLimitError
  │  └─ ProviderError
  ├─ BudgetExhaustedError
  ├─ MaxIterationsError
  └─ ConsensusFailedError
```

### Core Helpers

```python
# engine/_core.py (not public module, internal)

async def checked_complete(
    provider: LLMProvider, messages: Sequence[dict[str, Any]],
    budget: TokenUsage | None, **kwargs
) -> LLMResponse:
    """Check budget, call provider, record usage."""
    if budget and total_so_far >= budget.total_tokens:
        raise BudgetExhaustedError(...)
    return await provider.complete(messages, **kwargs)

async def gather_resilient(coros, max_concurrency=10) -> list[Any | BaseException]:
    """Partial results. Exceptions returned as values, not raised."""
    semaphore = asyncio.Semaphore(max_concurrency)
    async def run(coro):
        async with semaphore:
            return await coro
    return await asyncio.gather(*[run(c) for c in coros], return_exceptions=True)

async def gather_strict(coros, max_concurrency=10) -> list[Any]:
    """All-or-nothing. Single exceptions unwrapped from ExceptionGroup."""
    ...
```

### Dependencies
- `pydantic>=2.0,<3` (core)
- `openai>=1.0` (optional for OpenAI)
- Ollama provider: stdlib only

### Test Coverage Target
- 80% overall
- Edge cases, property-based tests on voting, concurrency tests
- Integration tests (marked `@pytest.mark.integration`, skipped in CI)

### Estimated LOC
- `provider.py`: 100 (protocols + LLMResponse + ToolCall)
- `types.py`: 80
- `_errors.py`: 30
- `_core.py`: 80 (helpers)
- `patterns.py`: 600 (4 patterns)
- `providers/_openai.py`: 80
- `providers/_ollama.py`: 100
- Tests: 400
- Examples: 200
- **Total: ~1700 LOC**

### README Expansion
- All 4 patterns documented
- 2 providers
- Cost tracking example
- Custom evaluator example

### Verification (SHIP GATE)
- [ ] All TIER 1 checks pass
- [ ] `pytest --cov-fail-under=80 -m "not integration"` passes
- [ ] All 4 patterns work with both providers
- [ ] Ollama example runs without OpenAI API key
- [ ] Union types validated on Pydantic inputs

### Git Release
- Tag: `v0.1.0-beta`
- Commit: `feat: add tree_of_thought, refine_loop, react_loop + Ollama provider`

---

## TIER 3: Full v0.1 (Anthropic + composition + documentation)

### Philosophy
Add remaining infrastructure: Anthropic provider, message conversion, pipe() composition, full docs.
Trace/progress still deferred to v0.2.

### Additional Files

```
src/executionkit/
  kit.py                   # Kit session object (optional convenience)
  compose.py               # pipe() operator
  engine/
    __init__.py
    parallel.py            # gather_resilient + gather_strict (public)
    retry.py               # RetryConfig + with_retry() (public for custom patterns)
  providers/
    _anthropic.py          # Anthropic SDK
    _conversion.py         # OpenAI ↔ Anthropic format (250 LOC of edge cases)
    _mock.py               # Configurable mock provider
docs/
  mkdocs.yml
  docs/
    index.md
    patterns.md
    providers.md
    composition.md
    api_reference.md
    examples.md
examples/
  (10 total: consensus, refine, tree_of_thought, react_loop, compose, custom_provider, custom_evaluator, error_handling, notebook, Jupyter)
```

### New Type Exports

```python
# TraceEntry added back (optional, only if on_progress callback used)
@dataclass(frozen=True, slots=True)
class TraceEntry:
    step: str              # "branch"/"sample"/"vote" etc.
    iteration: int
    input: str             # First 200 chars
    output: str            # First 500 chars
    score: float | None
    duration_ms: float
    tokens_used: int

# ProgressCallback (only if TraceEntry re-added)
ProgressCallback = Callable[[TraceEntry], None]

# VotingStrategy enum (optional)
class VotingStrategy(str, Enum):
    MAJORITY = "majority"
    WEIGHTED = "weighted"
```

### pipe() Operator

```python
async def pipe(
    provider: LLMProvider, prompt: str, *steps: Callable,
    max_budget: TokenUsage | None = None,
    **shared_kwargs: Any,
) -> PatternResult:
    """Chain patterns. Output of step N → prompt to step N+1.
    Costs/metadata merge. Budget shared (remaining passed to each step)."""
    ...
```

### Additional Providers

- **AnthropicProvider** — via `anthropic>=0.40`
- **MockProvider** — for testing, configurable failures
- **CustomProvider** — guide on adding your own

### Message Conversion (250 LOC)

All 9 edge cases from plan:
1. Multiple tool calls in single message
2. Assistant message with tool_calls but null content
3. Tool call ID format differences
4. Consecutive user/assistant alternation
5. System message extraction
6. Empty tool results
7. Unknown content blocks
8. Legacy `function_call` format rejection
9. `stop_reason` mapping

### Documentation

- **README.md** — hero example, install, all patterns, composition
- **CONTRIBUTING.md** — add-a-provider (5 steps), add-a-pattern (5 steps)
- **mkdocs** — auto-generated from Google-style docstrings
- **10 examples**

### Estimated Additional LOC
- `compose.py`: 80
- `kit.py`: 50
- `engine/`: 100 (parallel + retry extraction)
- `providers/_anthropic.py`: 120
- `providers/_conversion.py`: 250
- `providers/_mock.py`: 100
- Documentation: 300
- Additional examples: 300
- **Additional Total: ~1300 LOC**

### Total TIER 3 LOC: ~3000

### Verification (SHIP GATE)
- [ ] All TIER 2 checks pass
- [ ] Anthropic provider round-trips message format (9 edge cases tested)
- [ ] `pipe()` merges costs correctly
- [ ] All 4 patterns work with all 4 providers (16 combos, at least smoke-tested)
- [ ] Custom provider guide validates
- [ ] Full test coverage >80%

### Git Release
- Tag: `v0.1.0`
- Commit: `feat: full v0.1 release — Anthropic provider, composition, documentation`

---

## Decision Matrix

| Concern | TIER 1 | TIER 2 | TIER 3 |
|---------|--------|--------|--------|
| **Ship Date** | Tomorrow | This week | This month |
| **Core LOC** | ~250 | ~1700 | ~3000 |
| **Patterns** | 1 (consensus) | 4 | 4 |
| **Providers** | 1 (OpenAI) | 2 (OpenAI + Ollama) | 4 (+ Anthropic + Mock) |
| **Composition** | None | None | pipe() |
| **Tracing** | None | None | Deferred to v0.2 |
| **Docs** | Minimal | Good | Complete |
| **Message Conversion** | None | None | Yes |
| **Risk** | Low (1 pattern) | Medium (4 patterns) | Medium (conversion complexity) |
| **Market Signal** | Proves concept | Validates product-market fit | Full-featured beta |
| **Proof Points** | Voting works | All patterns work | Composability works |

---

## Recommended Path

**Ship TIER 1 immediately.** Takes 1-2 days. Proves concept.

**Then, in parallel:**
- **Track:** Does anyone use consensus? What's the feedback loop?
- **Build:** TIER 2 in 3-4 days (all 4 patterns are straightforward).
- **Polish:** TIER 3 message conversion only if Anthropic demand exists.

**If you skip Anthropic v0.1, defer pipe() until patterns are battle-tested.**

---

## Questions to Answer Before Starting

1. **Do you want to ship Friday (TIER 1) or Monday (TIER 2)?**
   - TIER 1 = proof of concept, clear signal to move fast or pivot
   - TIER 2 = launch-ready feature set, but more risk of bugs

2. **Is Anthropic support v0.1 or v0.2?**
   - If v0.2: TIER 2 ships faster, cleaner
   - If v0.1: budget 250 LOC more for conversion edge cases

3. **Do you want pipe() in v0.1 or v0.2?**
   - If v0.2: TIER 2 focuses on pattern stability
   - If v0.1: budget ~100 LOC for compose.py

4. **What's the primary validation signal?**
   - TIER 1: "Does consensus voting work and is the API intuitive?"
   - TIER 2: "Do all 4 patterns solve real use cases?"
   - TIER 3: "Does composability actually reduce code?"
