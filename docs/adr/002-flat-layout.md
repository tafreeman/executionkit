# ADR-002: Keep the package at the repository root

- Status: Accepted
- Date: 2026-05-11

## Context

The repository needed either a flat `executionkit/` package or a
`src/executionkit/` package.

## Decision

Keep `executionkit/` at the repository root and configure Hatchling to package
that directory.

## Consequences

- The source tree and import path are easy to locate.
- Running Python from the repository can import the working tree before it is
  installed.
- CI must test installation and package building so local imports do not hide
  packaging errors.

## Rejected alternative

A `src/` layout provides stronger protection against accidental working-tree
imports, but changing the established layout would create migration work
without changing the public API.
