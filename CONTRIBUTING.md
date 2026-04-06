# Contributing to ExecutionKit

Thanks for contributing. ExecutionKit is a minimal library — keep changes focused and test-first.

## Development Setup

```bash
git clone https://github.com/tafreeman/executionkit.git
cd executionkit
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify the install:

```bash
python -c "from executionkit import Provider, consensus, refine_loop, react_loop; print('OK')"
```

## Code Quality

Run these before every commit:

```bash
ruff check .
ruff format .
mypy --strict executionkit/
```

All three must pass cleanly. CI blocks on any failure.

## Testing

```bash
# Unit tests only (no real API calls)
pytest -m "not integration"

# With coverage — must stay above 80%
pytest --cov=executionkit --cov-fail-under=80

# Integration tests (requires real API keys)
OPENAI_API_KEY=sk-... pytest -m integration
```

Test files live in `tests/`. Use `MockProvider` from `executionkit._mock` in unit
tests — never make real API calls in non-integration tests.

## Code Style

**Immutability.** All value types are `@dataclass(frozen=True, slots=True)`. Never
mutate an existing object; return a new one instead.

**Type hints required.** Every function signature and class attribute must be
annotated. `mypy --strict` is enforced in CI. Avoid `Any` without justification.

**Functions under 50 lines.** Decompose larger functions unless readability
clearly suffers.

**No magic numbers.** Extract constants; use `RetryConfig` and `ConvergenceDetector`
for tunable parameters.

**Ruff enforced.** Rules active: `E, F, W, I, N, UP, S, B, A, C4, SIM, TCH, RUF`.
The linter replaces manual style debates.

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

1. Create a branch: `feature/`, `fix/`, `docs/`, or `chore/` prefix.
2. Write tests first (RED), then implement (GREEN), then refactor.
3. Run `ruff check .`, `mypy --strict executionkit/`, and `pytest --cov-fail-under=80`.
4. Open a PR with a description that covers: what changed, why, and how to verify.
5. One approval required before merge.

PRs should stay under 400 lines of diff where possible. For larger changes, open
an issue first to discuss scope.

## Anti-Scope

ExecutionKit is a pattern library, not a framework. Reject changes that add:

- Dashboard, routing, or spend-tracking UI
- Stateful graph runtimes or durable execution
- Native provider adapters beyond the OpenAI-compatible format
- Multi-agent handoff or orchestration primitives

If in doubt, open an issue before writing code.

## Security

- Never commit API keys, tokens, or `.env` files.
- All examples must read credentials from environment variables.
- Run `grep -r "sk-" examples/` before committing — no key literals.

## Need Help?

Open a GitHub issue. Tag it `question` for support, `bug` for defects,
`enhancement` for feature requests.
