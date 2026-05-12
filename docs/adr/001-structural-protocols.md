# ADR-001: Structural Protocols over Abstract Base Classes

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** During the v0.1 design review, the team needed to define the `LLMProvider` and `ToolCallingProvider` interfaces in a way that supported test doubles, custom implementations, and third-party clients without requiring inheritance from ExecutionKit base classes.

---

## Context and Problem Statement

ExecutionKit's three reasoning patterns (`consensus`, `refine_loop`, `react_loop`) each accept an `LLMProvider` as their first argument. The project needed a formal interface definition for this parameter — something that enforces the required `complete()` method signature and makes the type checkable.

Two approaches were available: Python's Abstract Base Classes (ABCs) from `abc.ABC`, or structural protocols from `typing.Protocol` (PEP 544, Python 3.8+). The choice has significant downstream effects on how users and test authors interact with the library.

The choice also interacts with a core design principle: zero runtime dependencies. The interface mechanism must not require any user-side import of ExecutionKit internals just to satisfy the interface.

## Decision Drivers

* Users should be able to pass any object with the right `complete()` method, without inheriting from an ExecutionKit class.
* The `MockProvider` test double must satisfy the interface without being coupled to the production protocol definition.
* Third-party clients (e.g., a wrapper around an Anthropic client) must satisfy the interface without modification.
* `isinstance()` checks must work at runtime for internal guards in `_TrackedProvider`.
* The zero-runtime-dependency design principle must not be compromised.

## Considered Options

* Option A: PEP 544 structural protocols (`typing.Protocol`)
* Option B: Abstract base classes (`abc.ABC` / `abc.ABCMeta`)

## Decision Outcome

**Chosen option:** Option A (structural protocols), because structural typing lets any conforming object satisfy the interface through duck typing while still enabling `isinstance()` checks via `@runtime_checkable`. Users and test authors never need to import or inherit from ExecutionKit classes.

### Positive Consequences

* Any object with the right method signatures satisfies `LLMProvider` — including `MockProvider`, custom wrappers, and third-party clients.
* `@runtime_checkable` enables `isinstance(provider, LLMProvider)` checks inside `_TrackedProvider.supports_tools` without requiring inheritance.
* Users implementing custom providers need zero imports from ExecutionKit at definition time; they only need to match the method signature.
* Consistent with Python's own standard library (`collections.abc`, `asyncio.Transport`) and popular third-party libraries.

### Negative Consequences

* IDEs may not always infer protocol conformance as clearly as ABC inheritance in all tool chains.
* Structural conformance is checked by type checkers (mypy) and at `isinstance()` call sites; a class with a subtly wrong signature silently does not conform rather than raising at class definition time.

## Pros and Cons of the Options

### Option A: Structural protocols (`typing.Protocol`)

* **Good:** Zero coupling — conforming objects need not import the protocol definition.
* **Good:** Satisfies the zero-dependency principle — no ExecutionKit imports required on the user side.
* **Good:** `@runtime_checkable` preserves `isinstance()` capability where needed.
* **Good:** Aligns with how Python's own stdlib defines abstract interfaces.
* **Bad:** Missing-method errors surface at call time or type-check time, not at class definition time.

### Option B: Abstract base classes (`abc.ABC`)

* **Good:** Subclasses that omit required methods raise `TypeError` immediately at instantiation.
* **Good:** IDE support for abstract method discovery is mature.
* **Bad:** Users must inherit from `ExecutionKit`'s `LLMProvider` ABC, coupling their code to our class hierarchy.
* **Bad:** Third-party clients cannot satisfy the interface without modification or a shim subclass.
* **Bad:** Contradicts the zero-dependency design — satisfying the interface requires importing from `executionkit`.
