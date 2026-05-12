# ADR-002: Flat Package Layout over src/ Wrapper

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** When initialising the repository structure, the team chose between placing `executionkit/` directly at the repo root (flat layout) or nesting it under a `src/` directory (src layout), a choice that affects developer ergonomics and install behaviour.

---

## Context and Problem Statement

Python projects can organise their package source in two common ways: the "flat" layout places the package directory at the repository root (`executionkit/` alongside `tests/` and `pyproject.toml`), while the "src" layout wraps it in an intermediate directory (`src/executionkit/`). Both are supported by modern build backends including Hatchling.

The src layout was designed to prevent a specific class of bug: accidentally importing the uninstalled source tree when `import executionkit` is run from the repo root, which can mask installation failures. The flat layout trades that protection for a simpler directory tree and faster development setup.

The right choice depends on the project's complexity, the depth of its dependency tree, and how it expects contributors to work.

## Decision Drivers

* New contributors should be able to run `pip install -e . && pytest` immediately after cloning with no extra steps.
* The library has zero required runtime dependencies, which eliminates the main risk scenario the src layout is designed to prevent.
* Consistency with widely-used Python OSS libraries reduces friction for experienced contributors.
* Simplicity is a first-class value; layout complexity must justify itself.

## Considered Options

* Option A: Flat layout (`executionkit/` at repo root)
* Option B: src layout (`src/executionkit/`)

## Decision Outcome

**Chosen option:** Option A (flat layout), because the primary benefit of the src layout — preventing accidental shadowing of installed packages — does not apply to a library with zero runtime dependencies. The flat layout removes one directory of indirection and matches the conventions of the Python libraries ExecutionKit is most similar to.

### Positive Consequences

* `import executionkit` resolves correctly immediately after `git clone && pip install -e .` with no path manipulation.
* Simpler directory tree — contributors immediately see `executionkit/` alongside `tests/` without navigating into `src/`.
* Consistent with the conventions of `requests`, `click`, `httpx`, and `attrs`, which share the zero-or-minimal-dependency profile.

### Negative Consequences

* Running `python -c "import executionkit"` from the repo root without installing first will succeed by accident (imports the source tree directly). This can mask a broken `pyproject.toml` entry point during development.
* If a future version adds heavy runtime dependencies with complex transitive trees, the src layout's shadow-prevention benefit becomes more relevant and this decision should be revisited.

## Pros and Cons of the Options

### Option A: Flat layout

* **Good:** Zero-friction setup — no editable-install tricks or PYTHONPATH manipulation needed.
* **Good:** Matches the established convention for minimal Python libraries.
* **Good:** One fewer directory level in navigation and import paths.
* **Bad:** The uninstalled source tree is importable from the repo root, which can hide packaging problems.

### Option B: src layout

* **Good:** Forces contributors to install before importing, surfacing packaging issues early.
* **Good:** Prevents accidental shadowing of a different installed version of the library.
* **Bad:** Adds a `src/` directory that serves no purpose for a zero-dependency library.
* **Bad:** Diverges from the conventions of well-known minimal Python libraries without a countervailing benefit.
* **Bad:** Requires contributors to understand why the extra directory exists before they can reason about the layout.
