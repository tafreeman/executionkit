# Contributing to ExecutionKit

Thanks for contributing. ExecutionKit is a minimal library — keep changes
focused and test-first.

## Dev Setup

```bash
git clone https://github.com/tafreeman/executionkit.git
cd executionkit
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify the install:

```bash
python -c "from executionkit import Provider, consensus, refine_loop, react_loop; print('OK')"
```

### Pre-commit hooks

Install once after cloning:

```bash
pip install pre-commit
pre-commit install
```

Hooks run automatically on `git commit`. What they check:

| Hook | Purpose |
|------|---------|
| `ruff` | Lint + auto-fix (E, F, W, I, N, UP, S, B, A, C4, SIM, TCH, RUF) |
| `ruff-format` | Consistent formatting |
| `mypy --strict` | Full type checking |
| `detect-private-key` | Block accidental key commits |
| `check-merge-conflict` | Block conflict markers |
| `end-of-file-fixer` | Ensure newline at EOF |
| `trailing-whitespace` | Strip trailing spaces |

To run hooks manually without committing:

```bash
pre-commit run --all-files
```

## Running the Test Suite

```bash
# Unit tests only — no real API calls
python -m pytest -m "not integration"

# With coverage report — must stay above 80%
python -m pytest --cov=executionkit --cov-fail-under=80

# Full integration tests (requires real API keys)
OPENAI_API_KEY=sk-... python -m pytest -m integration
```

Coverage is enforced in CI via `fail_under = 80` in `pyproject.toml`. New code
must include tests — follow TDD: write the test first (RED), implement to pass
(GREEN), then refactor (IMPROVE).

Use `MockProvider` from `executionkit._mock` in unit tests. Never make real API
calls in non-integration tests.

## Code Quality

Run these before every commit (or let pre-commit do it):

```bash
ruff check .
ruff format .
mypy --strict executionkit/
```

All three must pass. CI blocks on any failure. Bandit (`bandit -r executionkit/`)
also runs in CI for security scanning.

### Style rules

**Immutability.** All value types are `@dataclass(frozen=True, slots=True)`.
Never mutate an existing object; return a new one.

**Type hints required.** Every function signature and class attribute must be
annotated. `mypy --strict` is enforced. Avoid `Any` without justification.

**Functions under 50 lines.** Decompose larger functions unless readability
clearly suffers.

**No magic numbers.** Use `RetryConfig` and `ConvergenceDetector` for tunable
parameters; extract other constants.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full module map,
data-flow diagram, immutability contract, error hierarchy, and extension points.

Key modules:

| Module | Role |
|--------|------|
| `provider.py` | `LLMProvider` protocol, `Provider` class, error hierarchy |
| `types.py` | Frozen value types (`PatternResult`, `TokenUsage`, `Tool`) |
| `patterns/` | `consensus`, `refine_loop`, `react_loop` |
| `engine/` | `ConvergenceDetector`, retry, parallel, JSON extraction |
| `compose.py` | `pipe()` composition |
| `kit.py` | `Kit` session facade |

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`

Examples:

```
feat(patterns): add tree_of_thought pattern
fix(consensus): handle unanimous tie correctly
docs: add react_loop example
test(refine_loop): cover early convergence path
```

## PR Process

1. Branch from `main` using a `feature/`, `fix/`, `docs/`, or `chore/` prefix.
2. Write tests first (RED → GREEN → IMPROVE).
3. Ensure `ruff check .`, `mypy --strict executionkit/`, and
   `pytest --cov-fail-under=80` all pass.
4. Open a PR describing what changed, why, and how to verify.
5. One approval required before merge.

PRs should stay under 400 lines of diff. For larger changes, open an issue
first to discuss scope.

## Security

See [`SECURITY.md`](SECURITY.md) for the full security policy, including the
vulnerability reporting process and response SLAs.

Key rules for contributors:

- Never commit API keys, tokens, or `.env` files.
- All examples must read credentials from environment variables.
- Bandit runs in CI — do not add blanket `# noqa: S` suppressions without
  discussion.
- LLM output is untrusted. See the security doc for prompt injection and
  tool execution guidance.

## Anti-Scope

ExecutionKit is a pattern library, not a framework. Reject changes that add:

- Dashboard, routing, or spend-tracking UI
- Stateful graph runtimes or durable execution
- Native provider adapters beyond the OpenAI-compatible format
- Multi-agent handoff or orchestration primitives

If in doubt, open an issue before writing code.

## Need Help?

Open a GitHub issue. Tag it `question` for support, `bug` for defects,
`enhancement` for feature requests.
