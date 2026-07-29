---
name: release
description: Prepare and publish an ExecutionKit release through the repository workflows.
---

# Release ExecutionKit

Do not publish from a dirty tree or while required CI checks are failing.

## 1. Prepare the release

1. Run the full local validation skill.
2. Confirm required checks are green on the target commit.
3. Choose the semantic version:
   - major for an incompatible public API change;
   - minor for a backward-compatible feature;
   - patch for a backward-compatible fix.
4. Change `__version__` in `executionkit/__init__.py`.
5. Move the relevant `Unreleased` entries in `CHANGELOG.md` into
   `## [x.y.z] - YYYY-MM-DD`.
6. Leave an empty `Unreleased` section for later changes.
7. Re-run the full local validation skill.
8. Build the wheel and source distribution with `python -m build`.
9. Inspect the archive contents and confirm both report version `x.y.z`.

## 2. Commit and tag

Commit only the intended release changes:

```text
chore(release): x.y.z
```

Create the annotated release tag:

```bash
git tag -a vx.y.z -m "ExecutionKit x.y.z"
```

Push the release commit and that exact tag after review.

## 3. Automated publication

Pushing `v*` starts `.github/workflows/publish.yml`. The workflow:

1. re-runs release verification;
2. builds the distributions and an SBOM;
3. publishes through PyPI trusted publishing.

Do not add a PyPI API token. If publication fails, fix the workflow or trusted
publisher configuration and manually dispatch the existing tag ref. Do not
move or recreate a published tag.

Documentation is deployed by `.github/workflows/docs.yml` after successful CI
on `main`; do not push directly to `gh-pages`.

## 4. Create the GitHub release

After PyPI publication succeeds, create a GitHub release for `vx.y.z` using the
matching changelog section. Include behavior changes and migration steps
directly. Confirm the GitHub release, PyPI files, and documentation all point
to the same commit and version.
