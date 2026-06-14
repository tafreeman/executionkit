---
name: validate
description: Run the full local validation gate (lint + format + typecheck + tests) before pushing
---

Run all 4 steps in order. ALL must pass before the branch is safe to push.

## Step 1 — Lint check (ruff check)

Catches code errors, style violations, and anti-patterns.

```
python -m ruff check executionkit tests
```

If it fails: auto-fix what ruff can, then review the rest manually.

```
python -m ruff check --fix executionkit tests
```

## Step 2 — Format check (ruff format)

CRITICAL: This is a separate step from lint. CI has a dedicated "Format check (ruff)" job
that runs `ruff format --check`. Skipping this is a common cause of CI failures.

```
python -m ruff format --check executionkit tests
```

If it fails: reformat the files, then re-run the check.

```
python -m ruff format executionkit tests
```

## Step 3 — Type check (mypy)

Strict static analysis on the source package only. Tests are excluded in pyproject.toml,
so do NOT pass `tests/` or `.` — that triggers mypy-over-tests double-discovery in
editable-install mode and produces spurious errors.

```
python -m mypy executionkit
```

If it fails: investigate each error and fix the type annotation or logic. There is no
auto-fix; read the mypy output carefully.

## Step 4 — Test suite (pytest)

Runs all ~420 tests with 80% coverage enforcement (via pyproject.toml addopts).

```
python -m pytest -q
```

Quick run without coverage (faster feedback loop while iterating):

```
python -m pytest -q -o addopts=""
```

If tests fail: fix the failing tests or the implementation before pushing.

---

All 4 steps must show a clean exit before the branch is safe to push.
System Python 3.13 has all tools installed globally — no venv activation needed.
