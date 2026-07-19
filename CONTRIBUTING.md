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
# Unit tests and deterministic smoke tests — no real API calls
python -m pytest

# With coverage report — must stay above 80%
python -m pytest --cov=executionkit --cov-fail-under=80
```

Coverage is enforced in CI via `fail_under = 80` in `pyproject.toml`. New code
must include tests — follow TDD: write the test first (RED), implement to pass
(GREEN), then refactor (IMPROVE).

Use `MockProvider` from `executionkit._mock` in tests. The public test suite is
deterministic and does not call live LLM APIs; add a separately documented
manual smoke script before introducing provider-backed tests.

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

**Keep helpers small — under ~50 lines as a guideline, not a gate.** Decompose
larger functions unless readability clearly suffers. The long public pattern
entry points (`react_loop`, `refine_loop`, `map_reduce`, `checked_complete`) are
deliberate exceptions, and no CI rule enforces the limit.

**No magic numbers.** Use `RetryConfig` and `ConvergenceDetector` for tunable
parameters; extract other constants.

## Architecture

See [`docs/architecture.md`](https://github.com/tafreeman/executionkit/blob/main/docs/architecture.md) for the full module map,
data-flow diagram, immutability contract, error hierarchy, and extension points.

Key modules:

| Module | Role |
|--------|------|
| `provider.py` | `LLMProvider` protocol, `Provider` class, error hierarchy |
| `types.py` | Frozen value types (`PatternResult`, `TokenUsage`, `Tool`) |
| `patterns/` | `consensus`, `refine_loop`, `react_loop`, `structured`, `map_reduce` |
| `engine/` | `ConvergenceDetector`, retry, parallel, JSON extraction, messages, rate bucket, voting |
| `compose.py` | `pipe()` composition |
| `kit.py` | `Kit` session facade |
| `batches.py` | Anthropic Message Batches transport (`consensus_batch`, `map_batch`) |
| `mcp/` | stdlib stdio MCP server (`python -m executionkit.mcp`) |

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

See [`SECURITY.md`](https://github.com/tafreeman/executionkit/blob/main/SECURITY.md) for the full security policy, including the
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
- Multi-agent handoff or cross-agent orchestration — that tier lives in
  [agentic-runtime-platform](https://github.com/tafreeman/agentic-runtime-platform);
  ExecutionKit's `Router`/`Workflow`/`Plan`/`ApprovalGate` stay single-run
  composition primitives

If in doubt, open an issue before writing code.

## Need Help?

Open a GitHub issue. Tag it `question` for support, `bug` for defects,
`enhancement` for feature requests.

---

## Development Provenance & Verification

This repository is built solo with AI-assisted tooling. Because there is no second human reviewer, correctness is gated by **automated evidence**, not peer sign-off:

- **CI gates (every push / PR):** ruff, ruff-format, `mypy --strict`, `pytest --cov-fail-under=80`, Bandit, and pip-audit (2-OS × 3-Python matrix). Merges block on a red pipeline.
- **Behavioral verification:** the deterministic golden suite and the model-failure corpus (`tests/test_eval_goldens.py`, `tests/test_eval_failure_corpus.py`) run in normal CI and assert output correctness, not just coverage.
- **Provenance:** AI-assisted changes are verified against these gates before merge; the CI and evaluation output is the verification artifact of record.

Contributions are welcome via PR; CI must pass and changes should add or update tests.
