# Installation

ExecutionKit supports Python 3.11, 3.12, and 3.13.

## Create an environment

```bash
python -m venv .venv
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

In PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Install the base package

```bash
python -m pip install executionkit
```

The base install has no required third-party dependencies. `Provider` uses
the standard-library `urllib` transport.

Verify the install:

```bash
python -c "import executionkit; print(executionkit.__version__)"
```

## Optional extras

| Extra | Install command | Adds |
|---|---|---|
| `httpx` | `python -m pip install "executionkit[httpx]"` | An async HTTP client with connection pooling. `Provider` uses it automatically when installed. |
| `jsonschema` | `python -m pip install "executionkit[jsonschema]"` | Full JSON Schema validation for `react_loop()` tool arguments. |
| `otel` | `python -m pip install "executionkit[otel]"` | The OpenTelemetry API used by the package's span helpers. |
| `docs` | `python -m pip install "executionkit[docs]"` | MkDocs, the Material theme, Mermaid, and mkdocstrings. |
| `dev` | `python -m pip install "executionkit[dev]"` | Test, lint, type-check, coverage, build, and Bandit tools. |

The `jsonschema` extra matters when a tool schema uses features outside the
built-in top-level subset. Without the extra, those schemas fail closed before
the tool runs.

The `otel` extra contains the API used by library code. Tests or applications
that export spans also need an OpenTelemetry SDK and exporter chosen by the
application.

## Install from a checkout

```bash
git clone https://github.com/tafreeman/executionkit.git
cd executionkit
python -m pip install -e ".[dev,docs]" pip-audit
```

Run the standard checks:

```bash
python -m ruff check executionkit tests scripts
python -m mypy --strict executionkit
python -m pytest -q
python -m mkdocs build --strict
```

See [Contributing](../contributing.md) for the complete validation matrix.

## Next

- [Quick start](quickstart.md)
- [Provider setup](providers.md)
- [Pattern selection](../patterns/index.md)
