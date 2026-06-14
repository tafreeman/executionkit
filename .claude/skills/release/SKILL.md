---
name: release
description: Cut a new ExecutionKit release — version bump, changelog, tag, GitHub release, docs, PyPI
---

## Step 1 — Confirm CI is green

Run the local validation gate first. All four steps must pass.

```
/validate
```

Also confirm that the remote CI is green (GitHub Actions) before proceeding.

## Step 2 — Decide the new version

Semver rules:
- **major** (`x+1.0.0`) — breaking API change
- **minor** (`x.y+1.0`) — new backward-compatible feature
- **patch** (`x.y.z+1`) — bug fix or internal change only

Current version is in `executionkit/__init__.py` as `__version__`.

## Step 3 — Bump `__version__`

Edit `executionkit/__init__.py`:

```python
__version__ = "x.y.z"   # replace with new version
```

Hatchling reads the version from this file via `[tool.hatch.version] path = "executionkit/__init__.py"` — no `pyproject.toml` edit needed.

## Step 4 — Update CHANGELOG.md

Add a new section at the top of the file (above the previous release, below any `## [Unreleased]` block):

```markdown
## [x.y.z] — YYYY-MM-DD

### Added
- ...

### Fixed
- ...

### Changed
- ...
```

Keep the `## [Unreleased]` section below it (reset it to empty after moving its items into the new section).

## Step 5 — Validate again

```
/validate
```

Catches import errors introduced by the version bump before the commit is tagged.

## Step 6 — Commit

```
git add executionkit/__init__.py CHANGELOG.md
git commit -m "chore(release): x.y.z"
```

## Step 7 — Tag

```
git tag vx.y.z
```

## Step 8 — Push branch and tag

```
git push && git push --tags
```

## Step 9 — Create GitHub release

Extract the changelog notes for the new version and pass them directly:

```bash
gh release create vx.y.z \
  --title "vx.y.z" \
  --notes-file <(sed -n '/## \[x\.y\.z\]/,/## \[/p' CHANGELOG.md | head -n -1)
```

Alternative if process substitution is unavailable (e.g. plain PowerShell):

```bash
gh release create vx.y.z --generate-notes
# Then edit the release body in the browser to paste the CHANGELOG section
```

## Step 10 — Deploy docs

```
mkdocs gh-deploy --force
```

This pushes the rendered MkDocs site to the `gh-pages` branch.

## Step 11 — Build and publish to PyPI

Requires `PYPI_TOKEN` set in the environment (`export PYPI_TOKEN=pypi-...`).

```
python -m build
python -m twine upload dist/* -u __token__ -p "$PYPI_TOKEN"
```

Do NOT commit or log `PYPI_TOKEN`. Rotate it immediately if it is exposed.
