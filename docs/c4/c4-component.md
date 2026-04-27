# C4 Component Level: ExecutionKit

This document is the master index for all C4 Component-level documentation for the **ExecutionKit** Python library. Each component corresponds to a logical grouping of source modules with a coherent responsibility boundary.

## Components

| # | Component | Files | Responsibility |
|---|-----------|-------|----------------|
| 1 | [Provider Layer](c4-component-provider-layer.md) | `provider.py`, `errors.py`, `types.py` | LLM provider protocols, concrete HTTP client, all data types, error hierarchy |
| 2 | [Execution Engine](c4-component-execution-engine.md) | `engine/retry.py`, `engine/parallel.py`, `engine/convergence.py`, `engine/json_extraction.py` | Retry/backoff, bounded concurrency, convergence detection, JSON extraction |
| 3 | [Reasoning Patterns](c4-component-reasoning-patterns.md) | `patterns/consensus.py`, `patterns/refine_loop.py`, `patterns/react_loop.py`, `patterns/base.py` | Three composable LLM reasoning strategies with shared budget/cost base |
| 4 | [Composition & Session](c4-component-composition-session.md) | `compose.py`, `kit.py`, `cost.py`, `__init__.py` (sync wrappers) | Pipeline chaining, session defaults, cost tracking, sync convenience API |
| 5 | [Test & Dev Utilities](c4-component-test-dev-utilities.md) | `_mock.py`, `examples/` | Scripted mock provider, reference example scripts |

---

## Component Relationship Graph

The diagram below shows every component, the direction of dependency (arrow = "depends on"), and the key interface points.

```mermaid
---
title: ExecutionKit — C4 Component Relationships
---
flowchart TB
    subgraph EK["ExecutionKit"]
        direction TB

        subgraph PL["Provider Layer"]
            PLcore["LLMProvider / ToolCallingProvider\nProvider (HTTP client) / _classify_http_error\nLLMResponse / ToolCall\nPatternResult / TokenUsage / Tool\nVotingStrategy / Evaluator\nerrors.py: Exception hierarchy (9 classes)\nprovider.py re-exports exceptions via Name as Name"]
        end

        subgraph EE["Execution Engine"]
            EEcore["RetryConfig / with_retry / DEFAULT_RETRY\ngather_resilient / gather_strict\nConvergenceDetector\nextract_json / user_message / assistant_message"]
        end

        subgraph RP["Reasoning Patterns"]
            RPcore["consensus()\nrefine_loop()\nreact_loop()\nchecked_complete / _TrackedProvider"]
        end

        subgraph CS["Composition & Session"]
            CScore["pipe() / PatternStep\nKit\nCostTracker\n*_sync wrappers"]
        end

        subgraph TDU["Test & Dev Utilities"]
            TDUcore["MockProvider\nExample scripts"]
        end
    end

    %% Execution Engine depends on Provider Layer for exception types
    EE -->|ProviderError, RateLimitError| PL

    %% Reasoning Patterns depends on Provider Layer and Execution Engine
    RP -->|LLMProvider, ToolCallingProvider, LLMResponse, PatternResult, TokenUsage, exceptions| PL
    RP -->|with_retry, gather_strict, ConvergenceDetector, extract_json, user_message, assistant_message| EE
    RP -->|CostTracker| CS

    %% Composition & Session depends on Provider Layer and Reasoning Patterns
    CS -->|LLMProvider, PatternResult, TokenUsage, ExecutionKitError| PL
    CS -->|consensus, refine_loop, react_loop, pipe| RP

    %% Test & Dev Utilities depends on Provider Layer, Reasoning Patterns, and Composition & Session
    TDU -->|LLMResponse and LLMProvider contract| PL
    TDU -->|consensus, refine_loop, react_loop| RP
    TDU -->|Kit, pipe, *_sync wrappers| CS
```

---

## Dependency Direction Summary

| Component | Depends On | Depended on By |
|-----------|-----------|----------------|
| **Provider Layer** | _(none — foundation)_ | Execution Engine, Reasoning Patterns, Composition & Session, Test & Dev Utilities |
| **Execution Engine** | Provider Layer (exception types) | Reasoning Patterns |
| **Reasoning Patterns** | Provider Layer, Execution Engine, CostTracker from Composition & Session | Composition & Session, Test & Dev Utilities |
| **Composition & Session** | Provider Layer, Reasoning Patterns | Test & Dev Utilities |
| **Test & Dev Utilities** | Provider Layer, Reasoning Patterns, Composition & Session | _(none — leaf consumer)_ |

---

## Key Design Properties

- **Zero third-party runtime dependencies** — every component uses only the Python standard library at runtime
- **Protocol-based provider abstraction** — `LLMProvider` and `PatternStep` are `typing.Protocol` contracts; any conforming object plugs in without inheritance
- **Immutability by default** — `TokenUsage`, `PatternResult`, `LLMResponse`, `Tool`, `ToolCall`, and `RetryConfig` are all frozen dataclasses
- **Cost propagation on failure** — `ExecutionKitError` carries a `TokenUsage` cost field so callers can account for tokens consumed even when a pattern fails
- **Async-native, sync-bridged** — all patterns are `async`; Composition & Session provides `asyncio.run`-based sync wrappers for non-async callers
