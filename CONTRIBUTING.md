# Contributing to ExecutionKit

Keep changes small enough to review, add tests for behavior changes, and update
the documentation when a public contract changes.

## Set up the repository

```bash
git clone https://github.com/tafreeman/executionkit.git
cd executionkit
python -m venv .venv
```

Activate the environment on macOS or Linux:

```bash
source .venv/bin/activate
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the package, development tools, and documentation tools:

```bash
python -m pip install -e ".[dev,docs]" pip-audit
```

Verify the import:

```bash
python -c "import executionkit; print(executionkit.__version__)"
```

## Run the required checks

Run these commands from the repository root:

```bash
python -m ruff check executionkit tests scripts
python -m ruff format --check executionkit tests scripts
python -m mypy --strict executionkit
python scripts/check_doc_facts.py
python scripts/check_lock_parity.py
python -m pytest -q
python -m bandit -r executionkit -c pyproject.toml
python -m pip_audit --requirement requirements.lock
python -m mkdocs build --strict
```

`pytest` enforces branch coverage through `pyproject.toml` and fails below 80
percent. Tests marked `live` skip unless `EXECUTIONKIT_LIVE_EVAL=1`. Use the
following command when you need an explicit no-network test run:

```bash
python -m pytest -m "not live" -q
```

Focused test runs are useful while developing, but they do not replace the
full suite because the repository applies a package-wide coverage gate.

## Optional pre-commit hooks

Install the hooks once:

```bash
python -m pip install pre-commit
pre-commit install
```

Run them manually with:

```bash
pre-commit run --all-files
```

The hooks run Ruff, Ruff formatting, mypy, private-key detection, merge-marker
checks, whitespace fixes, and Gitleaks. The full commands in the previous
section remain the final local check.

## Testing rules

- Use `MockProvider` for unit tests that need model responses.
- Keep required tests offline and repeatable.
- Mark real-endpoint tests with `@pytest.mark.live`.
- Add a regression test for every fixed defect.
- Test error behavior and accounting, not only successful return values.
- When changing an optional integration, test both the installed and
  not-installed paths where practical.

`MockProvider` is part of the package's public test surface:

```python
from executionkit import MockProvider

provider = MockProvider(responses=["first response", "second response"])
```

## Code rules

- Add type annotations to public and internal function signatures.
- Keep `mypy --strict` clean.
- Do not mutate frozen result objects. Create a new value instead.
- Treat nested mappings carefully: a frozen dataclass prevents field
  reassignment but does not make every caller-supplied nested object immutable.
- Use named constants or configuration fields for behavior that callers may
  need to tune.
- Keep provider-independent behavior outside the concrete `Provider` class.
- Do not add a required runtime dependency without revisiting
  [ADR-004](https://tafreeman.github.io/executionkit/adr/004-zero-runtime-dependencies/).

## Documentation rules

Update documentation in the same change when you alter:

- a public import, signature, default, return value, metadata key, or exception;
- an environment variable or install extra;
- a command, workflow, or release step;
- provider compatibility or a security boundary; or
- the package scope.

Write for a software engineer who has not read the implementation. Define a
term before using it, prefer short sentences, and state limits next to
capabilities.

Run:

```bash
python scripts/check_doc_facts.py
python -m mkdocs build --strict
```

The documentation check compares public exports, pattern pages, tracked pages,
navigation, root-file includes, Python examples, and the architecture module
map with the source tree. The strict MkDocs build checks links and anchors.

`CONTRIBUTING.md`, `SECURITY.md`, and `CHANGELOG.md` are the source files for
their corresponding documentation-site pages. Edit the root file, not the
small include file under `docs/`.

## Architecture boundaries

| Area | Location |
|---|---|
| Public exports and sync wrappers | `executionkit/__init__.py` |
| Provider protocols and HTTP client | `executionkit/provider.py` |
| Result, usage, tool, and enum types | `executionkit/types.py` |
| Call patterns | `executionkit/patterns/` and `executionkit/compose.py` |
| Retry, parallelism, parsing, voting | `executionkit/engine/` |
| Session facade | `executionkit/kit.py` |
| Routing, workflow, planning, approval | `routing.py`, `workflow.py`, `planning.py`, `approval.py` |
| Evaluation and tracing | `evals.py`, `observability.py` |
| Anthropic batch integration | `executionkit/batches.py` |
| MCP stdio server | `executionkit/mcp/` |

ExecutionKit is an in-process library. Do not add dashboards, persistent
schedulers, retrieval storage, a native provider-adapter matrix, or
multi-agent coordination. Those concerns belong in the calling application or
a higher-level runtime.

Read the [architecture guide](https://tafreeman.github.io/executionkit/architecture/)
before changing a boundary between these areas.

## Commits and pull requests

Use a short Conventional Commit subject:

```text
feat(patterns): add bounded sampling mode
fix(workflow): reject duplicate step names
docs(api): document checkpoint resume
```

A pull request should explain:

1. the problem;
2. the behavior after the change;
3. compatibility or security effects; and
4. the exact commands used to verify it.

Avoid mixing unrelated cleanup into the same pull request.

## Security

Read the [security policy](https://github.com/tafreeman/executionkit/blob/main/SECURITY.md)
before changing HTTP handling, credential handling, tool execution, prompt
construction, serialization, subprocess use, or release workflows.

Do not commit credentials or realistic-looking placeholder secrets. Examples
must read credentials from environment variables. Do not weaken a security
check with a broad suppression; document the specific false positive and keep
the suppression as narrow as possible.

## Release changes

Add user-visible changes to the `Unreleased` section of
[CHANGELOG.md](https://github.com/tafreeman/executionkit/blob/main/CHANGELOG.md).
Call out behavior changes, migration steps, and new failure modes directly.

The release workflow publishes through PyPI trusted publishing. Do not add API
tokens to the workflow or repository.

## Questions

Use a [GitHub issue](https://github.com/tafreeman/executionkit/issues) for
usage questions, defects, or proposed changes. Report vulnerabilities through
the private channel described in the
[security policy](https://github.com/tafreeman/executionkit/blob/main/SECURITY.md).
