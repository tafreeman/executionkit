"""Doc-fact check: docs must not undercount the shipped package.

The 2026-07-06 portfolio audit found map_reduce, the MCP server, and the
Message Batches transport shipped and ADR-backed but missing from five doc
surfaces at once (README patterns table, mkdocs nav, patterns index,
architecture module map, CONTRIBUTING key-modules). This script derives the
shipped surface from ``executionkit/`` at run time and fails loud when a doc
surface disagrees, so the undercount class cannot recur silently.

Checks (all derived, nothing hand-maintained except SLUGS):
  1. every pattern module has a docs page, an mkdocs nav entry, a README
     patterns-table row, and a patterns-index table row;
  2. every docs/patterns/*.md page is reachable from the mkdocs nav;
  3. the patterns-index "N composable pattern utilities" claim equals the
     derived pattern count;
  4. every module in ``executionkit/`` is named in the architecture module
     map (basename granularity — a missing new module fails the check).

Stdlib only (ADR-004 discipline applies to tooling too). Run from the repo
root: ``python scripts/check_doc_facts.py``. Portfolio convention:
``docs/conventions/doc-fact-check.md`` at the workspace root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The one hand-maintained mapping: pattern module -> docs slug. A new pattern
# module without an entry here fails check 1 with a clear message.
SLUGS = {
    "consensus": "consensus",
    "map_reduce": "map-reduce",
    "react_loop": "react-loop",
    "refine_loop": "iterative-refinement",
    "structured": "structured",
    "pipe": "pipe",  # lives in compose.py, documented as a pattern
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

failures: list[str] = []


def read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8").replace("\r\n", "\n")


def derive_pattern_modules() -> set[str]:
    modules = {
        path.stem
        for path in (REPO_ROOT / "executionkit" / "patterns").glob("*.py")
        if path.stem not in {"__init__", "base"}
    }
    modules.add("pipe")
    return modules


def mkdocs_nav_pattern_pages() -> set[str]:
    """Pages listed under the 'Patterns:' nav section of mkdocs.yml.

    Assumes mkdocs.yml keeps its current 2-space top-level nav indentation;
    a reformat of the nav block would need the two regexes below updated.
    """
    lines = read("mkdocs.yml").split("\n")
    pages: set[str] = set()
    in_patterns = False
    for line in lines:
        if re.match(r"^  - Patterns:", line):
            in_patterns = True
            continue
        if in_patterns:
            if re.match(r"^  - \S", line):
                break
            entry = re.search(r":\s*(patterns/\S+\.md)\s*$", line)
            if entry:
                pages.add(entry.group(1))
    return pages


def check_patterns_documented(patterns: set[str], nav_pages: set[str]) -> None:
    readme = read("README.md")
    index = read("docs/patterns/index.md")
    for module in sorted(patterns):
        slug = SLUGS.get(module)
        if slug is None:
            failures.append(
                f"executionkit/patterns/{module}.py has no slug entry in "
                "scripts/check_doc_facts.py SLUGS — add the module's docs mapping"
            )
            continue
        if not (REPO_ROOT / "docs" / "patterns" / f"{slug}.md").exists():
            failures.append(
                f"pattern '{module}': docs/patterns/{slug}.md does not exist"
            )
        if f"patterns/{slug}.md" not in nav_pages:
            failures.append(
                f"pattern '{module}': patterns/{slug}.md missing from mkdocs nav"
            )
        if f"patterns/{slug}/" not in readme:
            failures.append(
                f"pattern '{module}': no row links patterns/{slug}/ in the README table"
            )
        if f"({slug}.md)" not in index:
            failures.append(
                f"pattern '{module}': no row links {slug}.md in docs/patterns/index.md"
            )


def check_nav_completeness(nav_pages: set[str]) -> None:
    for page in sorted((REPO_ROOT / "docs" / "patterns").glob("*.md")):
        if page.stem == "index":
            continue
        rel = f"patterns/{page.name}"
        if rel not in nav_pages:
            failures.append(f"docs/{rel} exists but is unreachable from the mkdocs nav")


def check_index_count_claim(patterns: set[str]) -> None:
    index = read("docs/patterns/index.md")
    claim = re.search(r"\*\*(\w+) composable pattern utilities\*\*", index)
    if claim is None:
        failures.append(
            "docs/patterns/index.md: the 'N composable pattern utilities' "
            "claim could not be found"
        )
        return
    claimed = NUMBER_WORDS.get(claim.group(1).lower())
    if claimed != len(patterns):
        failures.append(
            f"docs/patterns/index.md says '{claim.group(1)}' composable pattern "
            f"utilities; the package ships {len(patterns)}"
        )


def check_module_map_completeness() -> None:
    """Every shipped module must be named in the architecture module map.

    The map is a rendered tree, so a module's full relative path never appears
    as one contiguous string. Instead require BOTH tokens independently: the
    file's basename, and (for subpackage files) the ``<subpackage>/`` segment.
    This closes the basename-collision hole where one ``__init__.py`` mention
    satisfied all four packages, letting a brand-new subpackage slip through.
    Residual (accepted): the two tokens are not checked for adjacency, so a
    same-named file added to a second *already-documented* subpackage would
    still pass; parsing the tree layout is not worth it for this check.
    """
    architecture = read("docs/architecture.md")
    for path in sorted((REPO_ROOT / "executionkit").rglob("*.py")):
        in_subpackage = path.parent.name != "executionkit"
        named = path.name in architecture and (
            not in_subpackage or f"{path.parent.name}/" in architecture
        )
        if not named:
            rel = path.relative_to(REPO_ROOT).as_posix()
            failures.append(f"{rel} is not named in the architecture.md module map")


def main() -> int:
    patterns = derive_pattern_modules()
    nav_pages = mkdocs_nav_pattern_pages()
    check_patterns_documented(patterns, nav_pages)
    check_nav_completeness(nav_pages)
    check_index_count_claim(patterns)
    check_module_map_completeness()

    if failures:
        print(f"Doc-fact check failed ({len(failures)} issue(s)):", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        f"Doc-fact check passed: {len(patterns)} patterns documented across "
        "README, mkdocs nav, patterns index, and architecture module map."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
