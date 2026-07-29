---
name: validate
description: Run the local checks that match ExecutionKit CI and documentation gates.
---

# Validate the repository

Run from the repository root. Stop and fix a failure before treating the
branch as ready.

## Static checks

```bash
python -m ruff check executionkit tests scripts
python -m ruff format --check executionkit tests scripts
python -m mypy --strict executionkit
python scripts/check_lock_parity.py
```

## Documentation

```bash
python scripts/check_doc_facts.py
python -m mkdocs build --strict
```

The fact check compares public exports, maintained pages, pattern links,
navigation, root-file includes, and the architecture module map with the
repository.

## Tests

```bash
python -m pytest tests --cov=executionkit --cov-report=term-missing --cov-fail-under=80 -q
```

Normal tests are offline. Live-provider and model-judged evaluations are
separate opt-in workflows and are not substitutes for the deterministic suite.

## Security and package checks

```bash
python -m bandit -r executionkit -c pyproject.toml
python -m pip_audit --requirement requirements.lock
python -m build
```

`pip-audit` is installed separately from the project extras. Review any
reported advisory against the locked version and runtime use before changing a
dependency.
