"""Check documentation surfaces that can be derived from the repository.

The check is intentionally limited to facts that code can compare reliably:
public exports, shipped modules, tracked documentation pages, pattern pages,
navigation entries, and root-file includes. It does not score writing style or
attempt to infer semantic correctness.

Run from any directory with ``python scripts/check_doc_facts.py``.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Pattern implementations do not all share a file name with their public page.
# Adding a pattern module without a mapping fails with an actionable message.
PATTERN_SLUGS = {
    "consensus": "consensus",
    "map_reduce": "map-reduce",
    "pipe": "pipe",
    "react_loop": "react-loop",
    "refine_loop": "iterative-refinement",
    "structured": "structured",
}

ROOT_INCLUDES = {
    "docs/changelog.md": '--8<-- "CHANGELOG.md"',
    "docs/contributing.md": '--8<-- "CONTRIBUTING.md"',
    "docs/license.md": '--8<-- "LICENSE"',
    "docs/security.md": '--8<-- "SECURITY.md"',
}

failures: list[str] = []


def read(relative_path: str) -> str:
    """Read a repository file with normalized newlines."""
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8").replace("\r\n", "\n")


def git_paths(*arguments: str) -> set[str]:
    """Return repository-relative paths from one ``git ls-files`` query."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("git is required to run the documentation check")
    completed = subprocess.run(  # noqa: S603 - executable is resolved, arguments are internal
        [git_executable, "ls-files", *arguments],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    }


def maintained_doc_pages() -> set[str]:
    """Return tracked and new, non-ignored Markdown pages below ``docs``."""
    tracked = git_paths("--", "docs")
    new = git_paths("--others", "--exclude-standard", "--", "docs")
    return {
        path.removeprefix("docs/")
        for path in tracked | new
        if path.startswith("docs/") and path.endswith(".md")
    }


def maintained_markdown() -> set[str]:
    """Return all tracked and new, non-ignored Markdown files."""
    tracked = git_paths("--", "*.md")
    new = git_paths("--others", "--exclude-standard", "--", "*.md")
    return {path for path in tracked | new if path.endswith(".md")}


def nav_pages() -> set[str]:
    """Return Markdown page paths found in the MkDocs navigation."""
    return set(
        re.findall(
            r":\s*([A-Za-z0-9_./-]+\.md)\s*$",
            read("mkdocs.yml"),
            flags=re.MULTILINE,
        )
    )


def pattern_modules() -> set[str]:
    """Derive public pattern implementations from the package."""
    modules = {
        path.stem
        for path in (REPO_ROOT / "executionkit" / "patterns").glob("*.py")
        if path.stem not in {"__init__", "base"}
    }
    modules.add("pipe")
    return modules


def public_exports() -> tuple[str, ...]:
    """Read the literal package ``__all__`` without importing the package."""
    module = ast.parse(read("executionkit/__init__.py"))
    for statement in module.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in statement.targets
        ):
            value = ast.literal_eval(statement.value)
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                return tuple(value)
            break
    raise RuntimeError("executionkit/__init__.py has no literal string __all__ list")


def shipped_modules() -> set[str]:
    """Return tracked and new, non-ignored Python modules in the package."""
    tracked = git_paths("--", "executionkit")
    new = git_paths("--others", "--exclude-standard", "--", "executionkit")
    return {
        path
        for path in tracked | new
        if path.startswith("executionkit/") and path.endswith(".py")
    }


def check_nav() -> None:
    maintained = maintained_doc_pages()
    navigation = nav_pages()

    for page in sorted(maintained - navigation):
        failures.append(f"docs/{page} is maintained but missing from the MkDocs nav")

    for page in sorted(navigation - maintained):
        failures.append(f"MkDocs nav references missing or ignored docs/{page}")


def check_patterns() -> None:
    modules = pattern_modules()
    navigation = nav_pages()
    readme = read("README.md")
    landing = read("docs/index.md")
    index = read("docs/patterns/index.md")

    unknown = modules - PATTERN_SLUGS.keys()
    for module in sorted(unknown):
        failures.append(
            f"pattern module {module!r} has no PATTERN_SLUGS entry in "
            "scripts/check_doc_facts.py"
        )

    stale = PATTERN_SLUGS.keys() - modules
    for module in sorted(stale):
        failures.append(
            f"PATTERN_SLUGS contains {module!r}, but that implementation is absent"
        )

    for module in sorted(modules & PATTERN_SLUGS.keys()):
        slug = PATTERN_SLUGS[module]
        page = f"patterns/{slug}.md"
        if not (REPO_ROOT / "docs" / page).is_file():
            failures.append(f"pattern {module!r} is missing docs/{page}")
        if page not in navigation:
            failures.append(f"pattern {module!r} is missing {page} from MkDocs nav")
        if f"patterns/{slug}/" not in readme:
            failures.append(
                f"pattern {module!r} has no public README link to patterns/{slug}/"
            )
        if f"(patterns/{slug}.md)" not in landing:
            failures.append(
                f"pattern {module!r} has no link in docs/index.md to {page}"
            )
        if f"({slug}.md)" not in index:
            failures.append(f"pattern {module!r} has no link in docs/patterns/index.md")


def check_api_index() -> None:
    api_index = read("docs/api/index.md")
    for name in public_exports():
        if f"`{name}`" not in api_index:
            failures.append(f"public export {name!r} is missing from docs/api/index.md")


def check_architecture_modules() -> None:
    architecture = read("docs/architecture.md")
    for path in sorted(shipped_modules()):
        if f"`{path}`" not in architecture:
            failures.append(f"{path} is missing from the architecture module map")


def check_root_includes() -> None:
    for path, include in ROOT_INCLUDES.items():
        if include not in read(path):
            failures.append(f"{path} must include its root source with {include!r}")


def check_python_examples() -> None:
    """Compile Python fences, allowing the top-level ``await`` used in guides."""
    fence = re.compile(r"^```python\s*\n(.*?)^```\s*$", flags=re.MULTILINE | re.DOTALL)
    for path in sorted(maintained_markdown()):
        for index, match in enumerate(fence.finditer(read(path)), start=1):
            try:
                compile(
                    match.group(1),
                    f"{path}:python-block-{index}",
                    "exec",
                    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                )
            except SyntaxError as error:
                failures.append(
                    f"{path} Python block {index} has invalid syntax: "
                    f"{error.msg} at line {error.lineno}"
                )


def main() -> int:
    check_nav()
    check_patterns()
    check_api_index()
    check_architecture_modules()
    check_root_includes()
    check_python_examples()

    if failures:
        print(f"Doc-fact check failed ({len(failures)} issue(s)):", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        "Doc-fact check passed: "
        f"{len(maintained_doc_pages())} pages, "
        f"{len(pattern_modules())} patterns, "
        f"{len(public_exports())} public exports, and "
        f"{len(shipped_modules())} package modules are documented."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
