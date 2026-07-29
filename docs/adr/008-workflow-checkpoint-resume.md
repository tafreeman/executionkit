# ADR-008: Let callers persist workflow checkpoints

- Status: Accepted
- Date: 2026-06-18

## Context

A workflow can be interrupted after completing expensive steps. The library
needs a resume boundary without choosing a database or file format.

## Decision

After each batch of ready steps, `Workflow.run()` can pass a
`WorkflowCheckpoint` to a caller-supplied callback. The checkpoint contains
outputs completed so far and accumulated usage.

On resume, step names present in `checkpoint.outputs` are treated as complete.
The caller stores, loads, secures, and versions the serialized checkpoint.

## Consequences

- ExecutionKit remains storage-independent.
- Ready steps can still run concurrently.
- Workflow checkpoint callback exceptions propagate, so a caller can stop when
  durable persistence fails.
- Changed workflow definitions or output schemas require caller-managed
  migration checks.

## Rejected alternatives

Built-in file or database persistence would impose storage, locking, security,
and migration policies on every application.
