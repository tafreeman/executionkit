# ADR-008: Caller-Supplied Checkpoint Function for Workflow Resume

**Date:** 2026-06-18
**Status:** Accepted
**Deciders:** ExecutionKit core team
**Technical Story:** Workflow runs can be interrupted by process crashes, container evictions, or explicit cancellation. Users needed a way to resume from the last completed batch without re-executing costly LLM steps.

---

## Context and Problem Statement

`Workflow` executes steps in dependency-ordered batches. A run involving many
LLM-backed steps can take minutes and consume significant token budget. Without
a resume mechanism, any interruption restarts the entire workflow from scratch.

The design needed to satisfy three constraints simultaneously. First, the
library imposes zero runtime dependencies — no embedded database, file system
abstraction, or serialisation library was acceptable. Second, the storage
medium is caller-defined: some callers write checkpoints to JSON files, others
to a database row, others to in-memory state during tests. Third, the
checkpoint representation must be serialisation-friendly so any backend can
round-trip it without coupling to ExecutionKit internals.

## Decision Drivers

* Zero runtime dependencies — no persistence mechanism may be bundled.
* Callers choose their own storage backend; the library must not restrict that choice.
* Checkpoint data must be expressible in plain Python so JSON, pickle, and
  database backends all work without adaptation.
* Resume must be unambiguous: a step is skipped if and only if its output is
  already recorded in the checkpoint.
* The public API surface must remain small enough to test exhaustively with
  synchronous in-memory callbacks.

## Considered Options

* Option A: Caller-supplied `checkpoint_fn` called after each batch; plain-Python `to_dict` / `from_dict` on `WorkflowCheckpoint`
* Option B: Built-in file-based persistence with a configurable path
* Option C: No checkpointing support

## Decision Outcome

**Chosen option:** Option A (caller-supplied checkpoint function), because it
keeps persistence entirely outside the library while giving callers full
control over when, where, and how checkpoints are stored.

After each batch of completed steps, `Workflow.run` calls
`checkpoint_fn(WorkflowCheckpoint(...))` if one was provided. The caller
persists the checkpoint however it chooses. On the next run, the caller passes
`resume_from=WorkflowCheckpoint.from_dict(saved_data)`. Steps whose names
already appear in `checkpoint.outputs` are skipped; accumulated outputs and
token usage are restored verbatim.

`WorkflowCheckpoint.to_dict()` produces a plain-Python `dict` with only
`int`, `str`, and nested `dict` values — no ExecutionKit types. `from_dict`
reconstructs the dataclass from that same dict. The caller is responsible for
any additional serialisation (e.g., `json.dumps`).

### Positive Consequences

* Zero persistence dependency — the library ships nothing that writes to disk
  or a database.
* Any storage backend works: JSON file, SQLite row, Redis key, in-memory dict.
* `WorkflowCheckpoint` is a frozen dataclass; callers can safely hold
  references across async boundaries without defensive copies.
* Testing is straightforward — pass a list-appending lambda as `checkpoint_fn`
  and inspect the recorded checkpoints.

### Negative Consequences

* The caller must implement persistence boilerplate. There is no built-in
  helper for common cases like writing to a JSON file.
* If `checkpoint_fn` itself raises, the exception propagates out of
  `Workflow.run`. Callers must guard against storage failures inside the
  callback if they want the workflow to continue despite a failed checkpoint.

## Pros and Cons of the Options

### Option A: Caller-supplied checkpoint_fn

* **Good:** No storage dependency enters the library.
* **Good:** Works with any serialisation backend without adaptation.
* **Good:** Easily testable with a synchronous in-memory callback.
* **Bad:** Callers must write persistence boilerplate themselves.

### Option B: Built-in file-based persistence

* **Good:** Reduces boilerplate for the common case of single-process runs.
* **Bad:** Introduces an implicit dependency on the file system — incompatible
  with serverless environments, containers with read-only filesystems, or
  distributed workers.
* **Bad:** File paths and naming conventions become part of the public API,
  creating migration burdens.

### Option C: No checkpointing support

* **Good:** No added complexity.
* **Bad:** Every interruption restarts the entire workflow, wasting LLM budget
  and user time on long-running pipelines.
