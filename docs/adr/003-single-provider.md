# ADR-003: Use one OpenAI-compatible provider

- Status: Accepted
- Date: 2026-05-11
- Updated: 2026-07-28

## Context

Native adapters for every model provider would require separate request,
authentication, error, tool-call, and streaming implementations.

## Decision

Keep one general `Provider` for OpenAI-compatible chat-completions endpoints.
Use structural protocols for custom adapters maintained by callers.

The Anthropic Message Batches integration is a separate, narrow client because
that asynchronous API does not use the chat-completions shape. It does not
change the general provider boundary.

## Consequences

- Pattern code stays independent of provider SDKs.
- Endpoint and model compatibility are caller configuration.
- Native Anthropic, Azure deployment, Gemini, and other request shapes are not
  translated by the default provider.
- Provider-specific behavior is added only as a bounded integration with a
  documented reason.

## Rejected alternative

A native adapter matrix would broaden compatibility but add an ongoing
maintenance surface outside the package's pattern-execution purpose.
