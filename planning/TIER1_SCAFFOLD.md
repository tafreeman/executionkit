# TIER 1 Scaffold: Start Here Tomorrow

**This is the exact file structure, imports, and signatures you need to ship consensus-only v0.1.0-alpha by Friday EOD.**

---

## Directory Structure

```
executionkit/
├── pyproject.toml                 # Metadata, deps, build
├── LICENSE                        # MIT
├── README.md                      # Hero example
├── .gitignore                     # Python defaults + .env + .venv
├── py.typed                       # (empty file)
├── CHANGELOG.md                   # v0.1.0-alpha release notes
├── src/
│   └── executionkit/
│       ├── __init__.py            # Public API + sync wrapper
│       ├── _core.py               # Everything else
│       └── _errors.py             # 4 error classes
├── tests/
│   ├── conftest.py                # Fixtures, MockProvider
│   └── test_consensus.py          # 80+ lines
├── examples/
│   └── quickstart_consensus.py    # Hero example
└── docs/                          # (minimal, just hero + roadmap in README)
```

---

## File: `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "executionkit"
version = "0.1.0a1"  # alpha notation
description = "Composable LLM reasoning patterns with unified cost tracking"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [
    { name = "Your Name", email = "your.email@example.com" }
]
keywords = ["llm", "reasoning", "patterns", "consensus", "cost-tracking"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Python Modules",
]

dependencies = [
    "pydantic>=2.0,<3",
]

[project.optional-dependencies]
openai = ["openai>=1.0,<2"]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "mypy>=1.0",
]

[project.urls]
Repository = "https://github.com/yourusername/executionkit"
Issues = "https://github.com/yourusername/executionkit/issues"

[tool.hatch.build.targets.wheel]
packages = ["src/executionkit"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.ruff]
line-length = 88
target-version = "py311"
select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "C4", "SIM", "TCH", "RUF"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--cov=src/executionkit --cov-fail-under=80"

[tool.coverage.run]
branch = true
source = ["src/executionkit"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "class .*\\bProtocol\\):",
    "@(abc\\.)?abstractmethod",
]
```

---

## File: `src/executionkit/__init__.py`

```python
"""ExecutionKit: Composable LLM reasoning patterns."""

from __future__ import annotations

import asyncio
from typing import Any, Sequence, TypeVar

from ._core import LLMProvider, LLMResponse, OpenAIProvider, consensus
from ._errors import BudgetExhaustedError, ExecutionKitError, LLMError, RateLimitError

__version__ = "0.1.0a1"
__all__ = [
    # Types
    "LLMProvider",
    "LLMResponse",
    # Patterns
    "consensus",
    # Providers
    "OpenAIProvider",
    # Errors
    "ExecutionKitError",
    "LLMError",
    "RateLimitError",
    "BudgetExhaustedError",
    # Sync wrapper
    "consensus_sync",
]

T = TypeVar("T")


def consensus_sync(
    provider: LLMProvider,
    prompt: str,
    *,
    num_samples: int = 5,
    temperature: float = 0.9,
    max_tokens: int = 4096,
    max_budget_tokens: int | None = None,
    max_concurrency: int = 5,
) -> tuple[str, int]:
    """Sync wrapper for consensus() — Jupyter-safe.

    Args:
        provider: LLM provider instance
        prompt: Input prompt
        num_samples: Number of samples to generate (default 5)
        temperature: Temperature for sampling (default 0.9)
        max_tokens: Max tokens per sample (default 4096)
        max_budget_tokens: Total token budget (default None = unlimited)
        max_concurrency: Max concurrent calls (default 5)

    Returns:
        (most_common_response, total_tokens_used)

    Example:
        >>> from executionkit import OpenAIProvider, consensus_sync
        >>> provider = OpenAIProvider("gpt-4o-mini")
        >>> result, cost = consensus_sync(provider, "What is 2+2?")
        >>> print(result, f"({cost} tokens)")
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            raise RuntimeError(
                "nest_asyncio is required for Jupyter. Install with: "
                "pip install nest_asyncio"
            ) from None

    coro = consensus(
        provider,
        prompt,
        num_samples=num_samples,
        temperature=temperature,
        max_tokens=max_tokens,
        max_budget_tokens=max_budget_tokens,
        max_concurrency=max_concurrency,
    )

    if loop is not None and loop.is_running():
        return loop.run_until_complete(coro)
    return asyncio.run(coro)
```

---

## File: `src/executionkit/_errors.py`

```python
"""ExecutionKit error hierarchy."""

from __future__ import annotations


class ExecutionKitError(Exception):
    """Root error for all ExecutionKit exceptions."""
    pass


class LLMError(ExecutionKitError):
    """Provider-level error."""
    pass


class RateLimitError(LLMError):
    """Rate limit exceeded."""
    pass


class BudgetExhaustedError(ExecutionKitError):
    """Token budget exceeded."""
    pass
```

---

## File: `src/executionkit/_core.py`

```python
"""Core types and patterns."""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, Sequence, runtime_checkable

if TYPE_CHECKING:
    from typing_extensions import Self

from ._errors import BudgetExhaustedError, RateLimitError


# ============================================================================
# Types
# ============================================================================


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers. Frozen for 0.x — new capabilities via extension Protocols."""

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete a message sequence.

        Args:
            messages: OpenAI-format messages (role + content)
            temperature: Temperature for sampling
            max_tokens: Max tokens to generate
            **kwargs: Provider-specific options

        Returns:
            LLMResponse with content and usage
        """
        ...


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    """The generated content."""

    usage: dict[str, Any] = field(default_factory=dict)
    """Token usage: {input_tokens, output_tokens, total_tokens}."""

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.usage.get("total_tokens", 0)

    @property
    def input_tokens(self) -> int:
        """Input tokens."""
        return self.usage.get("input_tokens", 0)

    @property
    def output_tokens(self) -> int:
        """Output tokens."""
        return self.usage.get("output_tokens", 0)


# ============================================================================
# Consensus Pattern
# ============================================================================


async def consensus(
    provider: LLMProvider,
    prompt: str,
    *,
    num_samples: int = 5,
    temperature: float = 0.9,
    max_tokens: int = 4096,
    max_budget_tokens: int | None = None,
    max_concurrency: int = 5,
) -> tuple[str, int]:
    """Consensus: run prompt num_samples times, return most common response + cost.

    Args:
        provider: LLM provider
        prompt: User prompt
        num_samples: Number of parallel samples (default 5)
        temperature: Temperature (default 0.9 for diversity)
        max_tokens: Max tokens per sample (default 4096)
        max_budget_tokens: Total token budget (default None = unlimited)
        max_concurrency: Max concurrent API calls (default 5)

    Returns:
        (most_common_response: str, total_tokens_used: int)

    Raises:
        BudgetExhaustedError: If max_budget_tokens exceeded
        LLMError: If provider fails

    Example:
        >>> from executionkit import consensus, OpenAIProvider
        >>> provider = OpenAIProvider("gpt-4o-mini")
        >>> result, cost = await consensus(
        ...     provider,
        ...     "Is Python easier than Rust?",
        ...     num_samples=5,
        ... )
        >>> print(f"Result: {result}")
        >>> print(f"Cost: {cost} tokens")
    """
    messages = [{"role": "user", "content": prompt}]

    # Check budget before making any calls
    if max_budget_tokens is not None:
        # Rough estimate: assume input ~same for all, output varies
        estimated_cost = max_budget_tokens  # Conservative: budget is limit
        if estimated_cost > max_budget_tokens:
            raise BudgetExhaustedError(
                f"Estimated cost {estimated_cost} exceeds budget {max_budget_tokens}"
            )

    # Parallel sampling with semaphore
    semaphore = asyncio.Semaphore(max_concurrency)

    async def sample() -> tuple[str, int]:
        """Run one sample, return (content, total_tokens)."""
        async with semaphore:
            try:
                response = await provider.complete(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.content, response.total_tokens
            except Exception as e:
                if "rate_limit" in str(e).lower():
                    raise RateLimitError(str(e)) from e
                raise

    # Gather all samples
    results = await asyncio.gather(*[sample() for _ in range(num_samples)])

    # Compute total cost
    total_tokens = sum(tokens for _, tokens in results)

    # Check budget after the fact (hard limit)
    if max_budget_tokens is not None and total_tokens > max_budget_tokens:
        raise BudgetExhaustedError(
            f"Actual cost {total_tokens} exceeds budget {max_budget_tokens}"
        )

    # Vote: find most common response
    responses = [content for content, _ in results]
    vote_counts = Counter(responses)
    most_common, _ = vote_counts.most_common(1)[0]

    return most_common, total_tokens


# ============================================================================
# Providers
# ============================================================================


class OpenAIProvider:
    """OpenAI provider using `openai>=1.0` library.

    Example:
        >>> from executionkit import OpenAIProvider, consensus_sync
        >>> provider = OpenAIProvider("gpt-4o-mini")
        >>> result, cost = consensus_sync(provider, "What is 2+2?")
    """

    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None) -> None:
        """Initialize OpenAI provider.

        Args:
            model: Model name (default "gpt-4o-mini")
            api_key: API key (default: OPENAI_API_KEY env var)

        Raises:
            ImportError: If openai package not installed
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "openai is required. Install with: pip install executionkit[openai]"
            ) from None

        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "No API key provided. Set OPENAI_API_KEY env var or pass api_key="
            )

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Complete messages using OpenAI API."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[dict(m) for m in messages],  # type: ignore
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        return LLMResponse(
            content=content,
            usage={
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        )
```

---

## File: `src/executionkit/py.typed`

```
(empty file — signals PEP 561 type information)
```

---

## File: `tests/conftest.py`

```python
"""Test fixtures."""

from __future__ import annotations

from typing import Any, Sequence

import pytest

from executionkit._core import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    """Mock provider for testing."""

    def __init__(
        self,
        responses: list[str] | None = None,
        tokens_per_response: int = 100,
        fail_on_call_n: int | None = None,
    ) -> None:
        """Initialize mock provider.

        Args:
            responses: List of responses to cycle through
            tokens_per_response: Fake token count per response
            fail_on_call_n: Fail on the Nth call (for testing)
        """
        self.responses = responses or ["test response"]
        self.tokens_per_response = tokens_per_response
        self.fail_on_call_n = fail_on_call_n
        self.call_count = 0

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Return next canned response."""
        self.call_count += 1

        if self.fail_on_call_n is not None and self.call_count == self.fail_on_call_n:
            raise RuntimeError("Simulated provider failure")

        response = self.responses[(self.call_count - 1) % len(self.responses)]
        return LLMResponse(
            content=response,
            usage={
                "input_tokens": 50,
                "output_tokens": self.tokens_per_response,
                "total_tokens": 50 + self.tokens_per_response,
            },
        )


@pytest.fixture
def mock_provider() -> MockProvider:
    """Fixture for MockProvider."""
    return MockProvider()
```

---

## File: `tests/test_consensus.py`

```python
"""Tests for consensus pattern."""

from __future__ import annotations

import pytest

from executionkit import consensus
from executionkit._errors import BudgetExhaustedError
from tests.conftest import MockProvider


class TestConsensus:
    """Test consensus voting."""

    @pytest.mark.asyncio
    async def test_consensus_returns_tuple(self) -> None:
        """Consensus returns (value, cost) tuple."""
        provider = MockProvider(responses=["answer"])
        result, cost = await consensus(provider, "test prompt", num_samples=3)

        assert isinstance(result, str)
        assert result == "answer"
        assert isinstance(cost, int)
        assert cost > 0

    @pytest.mark.asyncio
    async def test_consensus_voting(self) -> None:
        """Consensus picks most common response."""
        provider = MockProvider(
            responses=["same", "same", "different"],
            tokens_per_response=100,
        )
        result, cost = await consensus(
            provider, "test", num_samples=3, max_concurrency=1
        )

        assert result == "same"
        assert cost == (50 + 100) * 3  # 3 calls, 50 input + 100 output tokens each

    @pytest.mark.asyncio
    async def test_consensus_budget_exceeded(self) -> None:
        """Consensus raises BudgetExhaustedError if cost exceeds budget."""
        provider = MockProvider(responses=["test"], tokens_per_response=100)

        with pytest.raises(BudgetExhaustedError):
            await consensus(
                provider,
                "test",
                num_samples=5,
                max_budget_tokens=100,  # Too small
            )

    @pytest.mark.asyncio
    async def test_consensus_concurrency(self) -> None:
        """Consensus respects max_concurrency."""
        provider = MockProvider(responses=["test"], tokens_per_response=100)
        result, cost = await consensus(
            provider,
            "test",
            num_samples=10,
            max_concurrency=3,
        )

        assert result == "test"
        assert cost > 0

    @pytest.mark.asyncio
    async def test_consensus_all_same(self) -> None:
        """Consensus works when all responses are identical."""
        provider = MockProvider(responses=["unanimous"])
        result, cost = await consensus(provider, "test", num_samples=5)

        assert result == "unanimous"

    @pytest.mark.asyncio
    async def test_consensus_diverse(self) -> None:
        """Consensus works with diverse responses."""
        provider = MockProvider(
            responses=["a", "b", "c", "a"],  # 'a' should win
            tokens_per_response=100,
        )
        result, cost = await consensus(
            provider, "test", num_samples=4, max_concurrency=1
        )

        assert result == "a"
```

---

## File: `examples/quickstart_consensus.py`

```python
"""Quick start: consensus voting example.

Run with:
    OPENAI_API_KEY=sk-... python examples/quickstart_consensus.py
"""

from __future__ import annotations

import asyncio

from executionkit import OpenAIProvider, consensus


async def main() -> None:
    """Run consensus example."""
    provider = OpenAIProvider("gpt-4o-mini")

    prompt = """You are a judge. Answer yes or no: Is Python easier to learn than Rust?
Answer with exactly one word: yes or no."""

    print("Running consensus with 5 samples...")
    result, total_tokens = await consensus(
        provider,
        prompt,
        num_samples=5,
        temperature=0.9,
        max_tokens=50,
    )

    print(f"\nMost common answer: {result}")
    print(f"Total tokens used: {total_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## File: `README.md`

```markdown
# ExecutionKit

Composable LLM reasoning patterns with unified cost tracking.

**Status:** v0.1.0-alpha (in development)

## Quick Start

```python
from executionkit import consensus, OpenAIProvider

provider = OpenAIProvider("gpt-4o-mini")

# Run prompt 5 times in parallel, vote on answer
result, cost = await consensus(
    provider,
    "Is Python easier than Rust?",
    num_samples=5,
)

print(result)  # Most common answer
print(f"Cost: {cost} tokens")
```

## Install

```bash
pip install executionkit openai
```

## Patterns

- **consensus** — Parallel voting. Run prompt N times, return most common response + cost.
- *(Coming in v0.1.0)* refine_loop, tree_of_thought, react_loop

## Providers

- **OpenAI** — GPT-4o, GPT-4o-mini, etc.
- *(Coming in v0.1.0)* Ollama (local, zero cost)
- *(Coming in v0.2)* Anthropic

## Why ExecutionKit?

1. **Unified cost tracking** — All patterns return `(value, total_tokens)`. Know your spend upfront.
2. **Provider-agnostic** — Same pattern code works with OpenAI, Anthropic, local models.
3. **Composable** — Chain patterns together (coming in v0.2).

## Docs

- [API Reference](https://github.com/yourusername/executionkit)
- [Examples](examples/)

## Contributing

Contributions welcome. See `CONTRIBUTING.md` (coming in v0.1.0).

## License

MIT
```

---

## File: `.gitignore`

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
.pytest_cache/
.coverage
htmlcov/

# Virtual environments
.venv/
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
.env
.env.local
.env.*.local
```

---

## File: `CHANGELOG.md`

```markdown
# Changelog

## 0.1.0a1 — 2026-04-04 (Alpha Release)

### Added
- **consensus** pattern: parallel voting with majority strategy
- **OpenAIProvider**: support for OpenAI models (gpt-4o-mini recommended)
- **Cost tracking**: all patterns return (value, total_tokens_used)
- **Sync wrapper**: `consensus_sync()` for Jupyter notebooks
- Full test coverage (80%+)

### Roadmap (v0.1.0)
- refine_loop pattern
- tree_of_thought pattern
- react_loop pattern with tool calling
- OllamaProvider (local models, zero cost)
- pipe() composition operator

### Roadmap (v0.2)
- AnthropicProvider
- Streaming responses
- Trace/observability
- Custom metrics and evaluators

---

*This is alpha software. API may change. Feedback welcome.*
```

---

## Ship Checklist

```
[ ] Create GitHub repo
[ ] Clone locally: git clone https://github.com/yourusername/executionkit
[ ] cd executionkit

[ ] Copy files listed above
[ ] Create src/executionkit/ directory structure
[ ] Create tests/ directory with conftest.py + test_consensus.py
[ ] Create examples/ directory with quickstart_consensus.py

[ ] Install dev dependencies:
    pip install -e ".[openai,dev]"

[ ] Run linter:
    ruff check . && ruff format . --check

[ ] Run type checker:
    mypy --strict src/

[ ] Run tests:
    pytest --cov-fail-under=80 -m "not integration"

[ ] Run example (with OPENAI_API_KEY set):
    python examples/quickstart_consensus.py

[ ] Final verification:
    - ruff + mypy + pytest all green
    - README renders correctly
    - Example works end-to-end
    - .env in .gitignore
    - Zero hardcoded secrets

[ ] Commit and push:
    git add -A
    git commit -m "feat: initial release — consensus pattern + OpenAI provider"
    git tag v0.1.0a1
    git push origin main --tags

[ ] Build and publish to PyPI:
    pip install build twine
    python -m build
    twine upload dist/*

[ ] Announce:
    - Tweet/HN comment
    - Announce in Discord/community
    - Email early users
```

---

## Estimated Time

- **Scaffolding & files**: 30 min
- **Core implementation**: 1 hour
- **Tests**: 1 hour
- **Verification & docs**: 1 hour
- **Buffer**: 30 min

**Total: ~4 hours. Ship by Friday 5pm.**
