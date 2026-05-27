# Installation

## Requirements

- Python **3.11+**
- An OpenAI-compatible LLM endpoint (OpenAI, Ollama, vLLM, GitHub Models, llama.cpp, Azure through a compatible gateway, etc.)

## From PyPI

```bash
pip install git+https://github.com/tafreeman/executionkit.git
```

This pulls **zero runtime dependencies** — the default backend is stdlib `urllib`.

## With connection pooling (`httpx`)

For high-throughput workloads (e.g. `consensus` with many samples, or long `react_loop` chains), install the optional `httpx` extra:

```bash
pip install "executionkit[httpx]"
```

The `Provider` automatically detects `httpx` at import time and uses an `httpx.AsyncClient` with connection pooling. With the stdlib backend, every LLM call opens a fresh TCP+TLS connection.

## Verify the install

```bash
python -c "from executionkit import Provider, consensus, refine_loop, react_loop; print('OK')"
```

## From source (development)

```bash
git clone https://github.com/tafreeman/executionkit.git
cd executionkit
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The `[dev]` extra adds `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `bandit`, `build`, and the optional `httpx` backend. See [Contributing](../contributing.md) for the full dev workflow.

## Build the docs locally

```bash
pip install -e ".[docs]"
mkdocs build --strict
```

The docs extra includes MkDocs Material, mkdocstrings, and Mermaid support used by the public site.

## Run the test suite

```bash
pytest -m "not integration"                              # unit tests, no API keys
pytest --cov=executionkit --cov-fail-under=80            # full suite with coverage
OPENAI_API_KEY=sk-... pytest -m integration              # live API tests
```

## Next

- [Quick Start](quickstart.md) — first call in 5 lines.
- [Provider Setup](providers.md) — configure OpenAI, Ollama, GitHub Models, Together, Groq, and Azure through a compatible gateway.
