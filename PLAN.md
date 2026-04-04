# ExecutionKit: Composable LLM Reasoning Patterns

## Context

The monorepo at `D:/source/prompts` was analyzed by 13+ specialized agents across 4 rounds to identify extractable standalone tools. The original concept ("Lithom" — structured LLM output SDK) was killed by 3 antagonistic reviewers because:
1. Native structured outputs from OpenAI/Anthropic/Google make JSON extraction obsolete
2. No competitive moat vs LiteLLM + Instructor (11K stars, 3M downloads)
3. 9-provider maintenance is unsustainable (~108 hrs/year)

The pivot: **ExecutionKit** — "itertools for LLM reasoning." Composable execution patterns (Tree of Thought, ReAct, consensus, refinement loops) where Python orchestrates real LLM calls.

**Why this wins:** No library owns this space. LangGraph requires graph wiring. DSPy focuses on optimization. Explicit GitHub demand signals (LangChain issues #11546, #23181, #34450). Agentic AI market growing 43.8% CAGR.

**Existing codebase provides 60% of the foundation** — 23 production-ready execution patterns already built in `agentic-workflows-v2/`.

---

## Package Structure

```
executionkit/
  pyproject.toml
  src/executionkit/
    __init__.py                 # Public: tree_of_thought, react_loop, consensus, refine_loop
    provider.py                 # LLMProvider Protocol + LLMResponse dataclass
    types.py                    # PatternResult[T], Branch, CostMetrics, Tool
    cost.py                     # CostTracker with per-pattern token/cost tracking
    patterns/
      __init__.py
      tree_of_thought.py        # branch -> evaluate -> prune -> recurse
      react_loop.py             # think -> act -> observe -> loop
      consensus.py              # call N times -> vote -> return best
      refine_loop.py            # generate -> evaluate -> improve -> converge
    _engine/
      __init__.py
      context.py                # Simplified ExecutionContext (from engine/context.py)
      retry.py                  # RetryConfig + backoff (from engine/step.py:18-68)
      parallel.py               # gather_bounded, race_first (from dag_executor.py)
      convergence.py            # NEW: delta threshold + plateau detection
    providers/                  # Minimal built-in providers (optional extras)
      __init__.py               # convenience: from executionkit.providers import OpenAIProvider
      _openai.py                # OpenAI + Azure + GitHub Models (all use openai SDK)
      _ollama.py                # Local Ollama via stdlib urllib (zero deps)
      _anthropic.py             # Claude (optional)
      _mock.py                  # MockProvider for testing (no deps)
  tests/
    conftest.py                 # MockProvider fixture, shared helpers
    test_tree_of_thought.py
    test_react_loop.py
    test_consensus.py
    test_refine_loop.py
    test_engine.py              # context, retry, parallel, convergence
    test_providers.py           # Built-in provider tests
  examples/
    basic_tot.py
    basic_react.py
    basic_consensus.py
    basic_refine.py
    quickstart_github.py        # 5-line example with GitHub Models
    quickstart_ollama.py        # 5-line example with local Ollama
```

**Dependencies:**
```toml
[project]
dependencies = ["pydantic>=2.0,<3"]

[project.optional-dependencies]
openai = ["openai>=1.0"]           # OpenAI + Azure + GitHub Models
anthropic = ["anthropic>=0.40"]     # Claude
all = ["executionkit[openai,anthropic]"]
dev = ["pytest>=7.0", "pytest-asyncio>=0.21", "pytest-cov>=4.0", "ruff>=0.4", "mypy>=1.10"]
```
Note: Ollama provider has zero extra deps (stdlib urllib). MockProvider has zero deps.

---

## Public API (4 Core Patterns)

### Provider Protocol — users implement this once

```python
# provider.py
@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: type | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...
```

### Built-in Providers (optional extras)

3 minimal providers ship with ExecutionKit so devs can start with just an API key:

**1. OpenAI-compatible** (`pip install executionkit[openai]`) — covers OpenAI, Azure, AND GitHub Models/Copilot since they all use the OpenAI SDK with different `base_url`:

```python
from executionkit.providers import OpenAIProvider

# GitHub Models — just an endpoint + token
provider = OpenAIProvider(
    model="gpt-4o-mini",
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],
)

# OpenAI — just a key
provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-...")

# Azure OpenAI — endpoint + key + deployment
provider = OpenAIProvider(
    model="my-deployment",
    base_url="https://myorg.openai.azure.com/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2024-10-21",
)

# Then use any pattern immediately
result = await tree_of_thought(provider, "Solve this problem...")
```

**2. Ollama** (`pip install executionkit` — zero extra deps, uses stdlib urllib):

```python
from executionkit.providers import OllamaProvider

# Local model — just a host (default localhost:11434)
provider = OllamaProvider(model="llama3.2")

# Remote Ollama
provider = OllamaProvider(model="mistral", host="http://gpu-server:11434")

result = await consensus(provider, "Classify this text...", num_samples=5)
```

**3. Anthropic** (`pip install executionkit[anthropic]`):

```python
from executionkit.providers import AnthropicProvider

provider = AnthropicProvider(model="claude-sonnet-4-20250514", api_key="sk-ant-...")
result = await react_loop(provider, "Research topic X", tools=[...])
```

**Key design decisions:**
- Each provider is ~50-80 lines — thin wrapper, not a framework
- `OpenAIProvider` covers 3 services via `base_url` param (OpenAI, Azure, GitHub Models)
- `OllamaProvider` uses stdlib `urllib` — zero pip dependencies for local-only use
- `MockProvider` always ships (in `_mock.py`) for testing — no deps
- All implement the same `LLMProvider` Protocol
- Source: adapted from `tools/llm/provider_adapters.py` (existing call_openai, call_ollama, call_claude functions)

### Pattern 1: `tree_of_thought()`

```python
result = await tree_of_thought(
    provider,
    prompt="Solve: what's 24 using 1,3,4,6?",
    num_branches=3,        # Generate 3 candidates per level
    beam_width=2,          # Keep top 2
    max_depth=3,           # 3 levels of reasoning
    evaluator=my_scorer,   # Custom scoring function
)
# result.value = best answer, result.cost = token/cost metrics
```

### Pattern 2: `react_loop()`

```python
result = await react_loop(
    provider,
    prompt="Find the CEO of the company that acquired Twitter",
    tools=[web_search, wikipedia_lookup],
    max_rounds=8,
)
```

### Pattern 3: `consensus()`

```python
result = await consensus(
    provider,
    prompt="Classify this text: ...",
    response_schema=Classification,
    num_samples=5,
    strategy="majority",
)
```

### Pattern 4: `refine_loop()`

```python
result = await refine_loop(
    provider,
    prompt="Write a haiku about recursion",
    evaluator=quality_scorer,
    target_score=0.9,
    max_iterations=5,
    patience=2,
)
```

All return `PatternResult[T]` with `.value`, `.score`, `.cost`, `.iterations`, `.trace`.

---

## What to Extract vs Write New

### EXTRACT from `agentic-workflows-v2/agentic_v2/`

| Target | Source File | Lines | What | Adaptation |
|--------|------------|-------|------|------------|
| `_engine/context.py` | `engine/context.py` | all | Variable store + child scoping + event hooks | Strip workflow_id, checkpoint, DI; keep var store + child() + events. ~120 LOC from ~450 |
| `_engine/retry.py` | `engine/step.py` | 18-68 | RetryConfig + backoff strategies | Extract verbatim. Self-contained 68 lines |
| `_engine/parallel.py` | `engine/dag_executor.py` | 194+ | FIRST_COMPLETED parallel scheduling | Generalize into `gather_bounded()` and `race_first()` helpers |
| `patterns/react_loop.py` | `engine/tool_execution.py` | 220-440 | Tool normalization, serialization, execution loop | Adapt from registry-based tools to `Tool` dataclass + `LLMProvider` |
| (fallback parser) | `agents/json_extraction.py` | all | Balanced-brace JSON extraction | Use as fallback when provider lacks structured output. 156 lines as-is |

### EXTRACT: Built-in Providers

| Target | Source File | Lines | Adaptation |
|--------|------------|-------|------------|
| `providers/_openai.py` | `tools/llm/provider_adapters.py` | 472-500 (call_openai) + 55-121 (call_azure_openai) | Merge into single class with `base_url` param. Add GitHub Models via base_url. ~70 LOC |
| `providers/_ollama.py` | `tools/llm/provider_adapters.py` | 16-52 (call_ollama) | Wrap in class implementing LLMProvider Protocol. Keep stdlib urllib. ~50 LOC |
| `providers/_anthropic.py` | `tools/llm/provider_adapters.py` | 446-469 (call_claude) | Wrap in class. ~50 LOC |
| `providers/_mock.py` | NEW | — | Canned responses for testing. ~30 LOC |

### WRITE NEW

| File | Est. LOC | Complexity | Why New |
|------|----------|------------|---------|
| `provider.py` | 60 | Low | LLMProvider Protocol + LLMResponse dataclass |
| `types.py` | 100 | Low | PatternResult, Branch, CostMetrics, Tool |
| `cost.py` | 120 | Medium | Structured cost-per-pattern tracking |
| `patterns/tree_of_thought.py` | 250 | **High** | Core new value — branch + evaluate + prune + recurse |
| `patterns/consensus.py` | 150 | Medium | Parallel sampling + voting aggregation |
| `patterns/refine_loop.py` | 180 | Medium | Loop + convergence detection |
| `_engine/convergence.py` | 80 | Medium | Delta threshold + plateau detection |

**Total new code: ~940 LOC. Total extracted+adapted: ~560 LOC. Grand total: ~1,500 LOC.**

---

## Phase Plan

### Phase 1: Foundation + Providers (Days 1-3)
- Scaffold package + pyproject.toml
- `provider.py` — LLMProvider Protocol + LLMResponse
- `types.py` — PatternResult, Branch, CostMetrics, Tool
- `cost.py` — CostTracker
- `providers/_openai.py` — extract from `provider_adapters.py:472-500`, add base_url for GitHub Models
- `providers/_ollama.py` — extract from `provider_adapters.py:16-52`, stdlib urllib
- `providers/_anthropic.py` — extract from `provider_adapters.py:446-469`
- `providers/_mock.py` — canned responses for testing
- `_engine/context.py` — simplified ExecutionContext (extract from `engine/context.py`)
- `_engine/retry.py` — extract RetryConfig from `engine/step.py:18-68`
- `_engine/parallel.py` — extract gather_bounded from `dag_executor.py`
- `_engine/convergence.py` — write convergence detector
- Tests: provider protocol, built-in providers, types, cost, convergence, parallel

### Phase 2: Core Patterns (Days 4-8)
Build order by complexity (simpler first):
1. **`consensus.py`** (Day 4) — simplest; tests provider + parallel infra
2. **`refine_loop.py`** (Day 5) — sequential loop; tests cost + convergence
3. **`react_loop.py`** (Days 6-7) — tool loop; extracts from `tool_execution.py`
4. **`tree_of_thought.py`** (Days 7-8) — most complex; depends on parallel + convergence
- Tests: 3 categories per pattern (unit with mocks, edge cases, integration markers)

### Phase 3: Polish + Release (Days 9-10)
- `__init__.py` — public exports
- Sync wrappers (`tree_of_thought_sync()`, etc.)
- JSON extraction fallback for non-structured providers
- Docstrings + README with 4 working examples
- CI: ruff + mypy --strict + pytest --cov-fail-under=80

### Phase 4: v0.2 Composition (Days 11-14, DEFER)
- `compose()` — chain patterns together
- OpenTelemetry integration (optional)
- LangGraph node adapter (optional)
- Streaming intermediate results

---

## Critical Source Files

- `D:/source/prompts/agentic-workflows-v2/agentic_v2/engine/context.py` — hierarchical context to simplify
- `D:/source/prompts/agentic-workflows-v2/agentic_v2/engine/dag_executor.py` — FIRST_COMPLETED parallel pattern
- `D:/source/prompts/agentic-workflows-v2/agentic_v2/engine/step.py` — RetryConfig (lines 18-68), loop_until (lines 353-368)
- `D:/source/prompts/agentic-workflows-v2/agentic_v2/engine/tool_execution.py` — ReAct tool loop (lines 373-440)
- `D:/source/prompts/agentic-workflows-v2/agentic_v2/agents/json_extraction.py` — balanced-brace extraction (fallback)

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Cost explosion** (ToT branches × depth = 100s of LLM calls) | `max_tokens` and `max_cost` params on every pattern. CostTracker checks budget BEFORE each call. Conservative defaults: beam_width=2, max_depth=3 |
| **Paradigm lock-in** (models add native reasoning) | Patterns are stateless functions, not framework classes. If models do ToT natively, users just stop calling the function |
| **Model churn** (prompts break across models) | All prompts overridable via params. `response_schema` forces structured output. JSON extraction fallback for messy responses |

---

## Test Strategy

Each pattern gets 3 test categories:
1. **Unit tests** — MockProvider returns canned responses. Verify message formation, loop termination, cost tracking
2. **Edge cases** — budget exhaustion, all branches pruned, max iterations, empty tool results, convergence on round 1
3. **Integration markers** — `@pytest.mark.integration` for real LLM calls (skipped in CI)

Coverage target: 80% overall, 90% for pattern modules.

---

## Agent Team Build Assignments

| Agent | Phase | Files |
|-------|-------|-------|
| **tdd-guide** | 1-3 | Write tests FIRST for each module |
| **build-agent-1** | 1 | Package scaffold, provider.py, types.py, cost.py, _engine/* |
| **build-agent-2** | 2 | consensus.py, refine_loop.py |
| **build-agent-3** | 2 | react_loop.py (extract from tool_execution.py), tree_of_thought.py |
| **code-reviewer** | 3 | Final review of all modules |
| **security-reviewer** | 2 | Audit expression eval if included, JSON extraction DoS limits |

---

## Verification

1. `ruff check src/executionkit` — lint passes
2. `mypy --strict src/executionkit` — type check passes
3. `pytest tests/ --cov=executionkit --cov-fail-under=80` — all tests pass, 80%+ coverage
4. Run `examples/quickstart_github.py` with `GITHUB_TOKEN` — 5-line hello world works end-to-end
5. Run `examples/quickstart_ollama.py` with local Ollama — works with zero cloud deps
6. Run `examples/basic_tot.py` with a real provider — produces valid tree with scores
7. Run `examples/basic_react.py` with mock tools — completes think/act/observe loop
8. Run `examples/basic_consensus.py` — returns majority vote from 5 samples
9. Run `examples/basic_refine.py` — converges within max_iterations

### Quickstart Smoke Test (the "30-second experience")

```python
# examples/quickstart_github.py
from executionkit import consensus
from executionkit.providers import OpenAIProvider

provider = OpenAIProvider(
    model="gpt-4o-mini",
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],
)

result = await consensus(provider, "What is 2+2?", num_samples=3)
print(result.value)  # "4"
print(result.cost)   # CostMetrics(input_tokens=45, output_tokens=9, llm_calls=3)
```
