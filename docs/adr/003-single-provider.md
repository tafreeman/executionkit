# ADR-003: Single OpenAI-Compatible Provider over Native Adapter Matrix

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** The v0.1 scope review identified "provider-matrix creep" as one of three named anti-scope guardrails; the team locked the provider design to a single `Provider` class targeting the OpenAI-compatible `/chat/completions` endpoint, deferring any native adapters to a future release.

---

## Context and Problem Statement

LLM libraries commonly provide a separate adapter for each major provider (OpenAI, Anthropic, Gemini, Cohere, etc.), each handling the provider's unique request format, authentication scheme, and response shape. This approach maximises out-of-the-box compatibility but creates a permanent maintenance commitment: every new provider model, API version, or format change requires a library update.

ExecutionKit needed to decide how broad its provider support should be at v0.1. The library's value proposition is composable reasoning patterns with budget awareness — not provider portability. A large adapter matrix would shift the identity of the project toward "universal gateway", which is explicitly out of scope.

## Decision Drivers

* Provider-matrix creep is one of three named Anti-Scope Guardrails in the build specification; the team committed to rejecting it at design time.
* The OpenAI `/chat/completions` JSON format has become a de facto standard: OpenAI, Ollama, LM Studio, vLLM, Groq, Mistral, Fireworks, Together AI, GitHub Models, and Azure deployments behind compatible gateways all expose a compatible endpoint shape.
* Each native adapter (Anthropic Messages API, Gemini GenerateContent, etc.) requires ongoing maintenance and testing against a live API.
* The `LLMProvider` structural protocol allows users to implement their own adapters without any changes to ExecutionKit.

## Considered Options

* Option A: Single `Provider` class targeting the OpenAI-compatible HTTP API
* Option B: Native adapter per major provider (OpenAI, Anthropic, Gemini, Ollama, ...)

## Decision Outcome

**Chosen option:** Option A (single Provider), because one class targeting the OpenAI-compatible format reaches the majority of commercial and local LLM endpoints with no additional code. Anthropic native support is deferred to v0.2, where a message-format converter can be added cleanly. Users who need Anthropic today can route through a compatible proxy such as LiteLLM.

### Positive Consequences

* A single `Provider(base_url, api_key, model)` constructor works against OpenAI, Ollama, Groq, Together AI, LM Studio, vLLM, Azure through compatible gateways, and any other OpenAI-compatible endpoint using bearer-token authentication.
* The library's identity stays focused on reasoning patterns, not provider plumbing.
* Eliminates an entire class of maintenance work: no per-provider test suites, no per-provider API version tracking.
* Users can implement their own `LLMProvider`-conforming adapter for any non-compatible provider without waiting for a library release.

### Negative Consequences

* Anthropic's Claude models are not directly supported in v0.1. Users need LiteLLM or a compatible proxy as a stopgap.
* Providers whose responses deviate from the OpenAI JSON shape (non-standard field names, missing `usage`, etc.) require workarounds in the single provider's response parser.
* The decision to defer Anthropic was scope-driven, not technical; this creates an expectation of native support in v0.2 that must be managed.

## Pros and Cons of the Options

### Option A: Single OpenAI-compatible Provider

* **Good:** One class covers the majority of endpoints in use today (OpenAI, Groq, Ollama, vLLM, LM Studio, Together AI, Fireworks, Mistral, GitHub Models, and Azure through compatible gateways).
* **Good:** Zero maintenance overhead for providers that don't need their own adapter.
* **Good:** The `LLMProvider` protocol acts as an extension point — anyone can implement a native adapter as a drop-in without forking the library.
* **Bad:** Anthropic and Gemini native APIs are not covered; users need a proxy or a custom implementation.

### Option B: Native adapter matrix

* **Good:** Out-of-the-box support for all major providers without a proxy.
* **Good:** Each adapter can take advantage of provider-specific features (extended thinking, grounding, cached content headers, etc.).
* **Bad:** Each adapter is a permanent maintenance commitment: API versions change, authentication schemes update, response shapes diverge.
* **Bad:** Positions the library as a provider gateway, which is explicitly outside its scope and competes with LiteLLM and the OpenAI Agents SDK.
* **Bad:** "Supports everything" messaging is listed as a de-emphasis guardrail in the build specification; building the matrix contradicts the project's stated positioning.
