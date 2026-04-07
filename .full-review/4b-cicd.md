# Phase 4B: CI/CD & DevOps Review

**Reviewer:** cicd-reviewer (DevOps Engineer)
**Date:** 2026-04-06
**Scope:** CI pipeline, publish workflow, build configuration, dependency management, security scanning, release process, pre-commit hooks, developer workflow
**Files reviewed:** `.github/workflows/ci.yml`, `.github/workflows/publish.yml`, `.github/dependabot.yml`, `.pre-commit-config.yaml`, `pyproject.toml`, `CONTRIBUTING.md`, `SECURITY.md`, `.gitignore`

---

## Executive Summary

ExecutionKit's CI/CD setup is solid for a v0.1.0 library. The CI pipeline covers linting, formatting, type checking, tests with coverage enforcement, and SAST scanning across a 2x3 build matrix. The publish workflow correctly uses OIDC trusted publishing -- the gold standard for PyPI releases. Dependabot is configured for both pip and GitHub Actions ecosystems.

The main gaps are: no CI gate linking the publish workflow to CI passing, no changelog or version-tag verification in the release process, stale pre-commit hook versions, and missing pipeline stages for coverage artifact upload and dependency vulnerability scanning.

| Severity | Count |
|----------|-------|
| Critical | 0     |
| High     | 3     |
| Medium   | 6     |
| Low      | 5     |
| **Total** | **14** |

---

## High

### CD-H1: Publish workflow has no CI gate

**File:** `.github/workflows/publish.yml`
**Category:** Release safety

The publish workflow triggers on `push tags: ["v*"]` and runs `build` then `publish` jobs. The `publish` job depends only on `build` (line 34: `needs: build`). There is **no dependency on the CI workflow passing**. A maintainer can push a `v*` tag on a commit where CI is failing -- the package will build and publish to PyPI regardless.

This means:
- A release with failing tests can reach PyPI
- A release with lint/type errors can reach PyPI
- A release with security scan failures can reach PyPI

**Recommendation:** Add a `ci` job requirement to the publish workflow using `workflow_run` or by converting to a reusable workflow pattern:

```yaml
# Option A: Add a CI check job to publish.yml
jobs:
  ci-check:
    name: Verify CI passed
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check CI status
        run: |
          gh run list --workflow=ci.yml --branch=${{ github.ref_name }} \
            --status=success --limit=1 --json conclusion -q '.[0].conclusion' \
            | grep -q success || { echo "CI has not passed for this ref"; exit 1; }
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  build:
    needs: ci-check
    # ... existing build steps
```

Or more robustly, trigger CI on tag pushes as well and make `publish` depend on the CI workflow completing:

```yaml
# In ci.yml, add tag trigger:
on:
  push:
    branches: [main]
    tags: ["v*"]
  pull_request:
    branches: [main]
```

Then in `publish.yml` use `workflow_run`:

```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]
    # Filter to v* tags in the job
```

---

### CD-H2: No version-tag consistency verification

**File:** `.github/workflows/publish.yml`, `pyproject.toml:52-53`
**Category:** Release integrity

The version is sourced dynamically from `executionkit/__init__.py` (`__version__ = "0.1.0"`) via Hatch's `[tool.hatch.version]` config. But the publish workflow does not verify that the git tag matches the package version. A maintainer could:

1. Tag `v0.2.0` on a commit where `__version__ = "0.1.0"`
2. The package publishes to PyPI as `executionkit-0.1.0` under the `v0.2.0` tag
3. The git tag and PyPI version diverge permanently

**Recommendation:** Add a version consistency check to the build job:

```yaml
- name: Verify tag matches package version
  run: |
    TAG_VERSION="${GITHUB_REF#refs/tags/v}"
    PKG_VERSION=$(python -c "import executionkit; print(executionkit.__version__)")
    if [ "$TAG_VERSION" != "$PKG_VERSION" ]; then
      echo "::error::Tag version ($TAG_VERSION) does not match package version ($PKG_VERSION)"
      exit 1
    fi
```

---

### CD-H3: Pre-commit hook versions are severely outdated

**File:** `.pre-commit-config.yaml`
**Category:** Developer tooling drift

The pre-commit hooks pin old versions that are far behind the CI versions:

| Hook | Pre-commit version | CI / pyproject version | Gap |
|------|-------------------|----------------------|-----|
| ruff | `v0.4.0` | `>=0.14.0,<0.15` | ~10 minor versions behind |
| mypy | `v1.10.0` | `>=1.18` | ~8 minor versions behind |
| pre-commit-hooks | `v4.6.0` | (latest ~v5.0) | ~1 major version behind |

**Impact:** Developers running `pre-commit` locally get different lint results than CI. A commit that passes local pre-commit hooks can fail CI, or vice versa. This defeats the purpose of pre-commit hooks as a local CI preview.

**Recommendation:** Update `.pre-commit-config.yaml` to match CI tool versions:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.18.0
    hooks:
      - id: mypy
        args: [--strict]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: detect-private-key
      - id: check-merge-conflict
      - id: end-of-file-fixer
      - id: trailing-whitespace
```

Also consider adding `pre-commit autoupdate` to a scheduled CI job or Dependabot-like automation for pre-commit hooks (e.g., `pre-commit.ci` or a scheduled GitHub Action).

---

## Medium

### CD-M1: No dependency vulnerability scanning in CI

**File:** `.github/workflows/ci.yml`
**Category:** Supply chain security

The CI pipeline runs Bandit for SAST (static analysis of source code) but has no dependency vulnerability scanning. While ExecutionKit has zero runtime dependencies (excellent), the dev dependencies are installed in CI and could contain known vulnerabilities. More importantly, when users install `executionkit[httpx]`, the transitive dependencies of `httpx` are not scanned.

Dependabot (`.github/dependabot.yml`) handles version bumps but does not block CI on known CVEs -- it only opens PRs.

**Recommendation:** Add a dependency scanning step to the CI pipeline:

```yaml
  dependency-check:
    name: "Dependency vulnerability scan"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install pip-audit
        run: pip install pip-audit
      - name: Audit dependencies
        run: |
          pip install -e ".[dev]"
          pip-audit --strict
```

This catches known CVEs in installed packages and blocks the pipeline if any are found.

---

### CD-M2: No coverage artifact upload or trend tracking

**File:** `.github/workflows/ci.yml:39-40`
**Category:** Observability

The CI pipeline runs `pytest --cov-fail-under=80` which enforces a minimum threshold, but:
- Coverage reports are not uploaded as artifacts
- No coverage badge or trend tracking
- Coverage is only visible in the CI log output (`--cov-report=term-missing`)
- No XML/JSON report for integration with coverage services (Codecov, Coveralls)

If coverage drops from 83% to 81%, CI still passes and nobody notices the trend.

**Recommendation:** Add coverage report upload:

```yaml
- name: Tests with coverage
  run: pytest tests/ --cov=executionkit --cov-report=term-missing --cov-report=xml --cov-fail-under=80 -x -q

- name: Upload coverage report
  if: matrix.python-version == '3.12' && matrix.os == 'ubuntu-latest'
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: coverage.xml
```

Consider integrating with Codecov or Coveralls for trend tracking and PR comments showing coverage delta.

---

### CD-M3: Security scan (Bandit) runs independently of test job

**File:** `.github/workflows/ci.yml:42-57`
**Category:** Pipeline structure

The `security` job runs independently of the `test` job -- they execute in parallel with no dependency relationship. This is fine for speed, but it means:

1. **No required status check coordination.** If branch protection requires only the `test` job, a Bandit failure is invisible to merge gates. Both `test` AND `security` must be listed as required status checks in GitHub branch protection settings.

2. **Bandit installs separately.** The security job installs `bandit[toml]` directly rather than using the `[dev]` extra, which already includes `bandit[toml]>=1.8`. This means the Bandit version in CI might differ from the one developers use locally.

**Recommendation:**
- Ensure both `test` and `security` are configured as required status checks in GitHub branch protection.
- Consider using `pip install -e ".[dev]"` in the security job for version consistency:

```yaml
  security:
    name: "Security scan (Bandit)"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: bandit -r executionkit/ -c pyproject.toml
```

---

### CD-M4: No changelog verification in release process

**File:** `.github/workflows/publish.yml`, `CHANGELOG.md` (not reviewed but referenced)
**Category:** Release documentation

The release process has no automated check that the CHANGELOG has been updated for the release version. Combined with Phase 3's finding (D-L1) that the CHANGELOG is "nearly empty" with only "Initial release.", there is no mechanism to ensure releases are documented.

**Recommendation:** Add a changelog check to the publish workflow or a dedicated CI step:

```yaml
- name: Verify CHANGELOG updated for release
  run: |
    TAG_VERSION="${GITHUB_REF#refs/tags/v}"
    if ! grep -q "$TAG_VERSION" CHANGELOG.md; then
      echo "::error::CHANGELOG.md does not contain an entry for version $TAG_VERSION"
      exit 1
    fi
```

---

### CD-M5: Build matrix missing macOS

**File:** `.github/workflows/ci.yml:13-15`
**Category:** Platform coverage

The build matrix covers `ubuntu-latest` and `windows-latest` across Python 3.11/3.12/3.13 (6 combinations). macOS is not included. Since ExecutionKit is a pure-Python library with no native extensions, macOS failures are unlikely but not impossible -- differences in `asyncio` event loop behavior (e.g., `kqueue` vs `epoll`), file encoding defaults, and stdlib behavior can cause platform-specific bugs.

**Recommendation:** Add `macos-latest` to the matrix. Since it increases the matrix to 9 jobs, consider running macOS only on the latest Python version to manage CI minutes:

```yaml
matrix:
  os: [ubuntu-latest, windows-latest]
  python-version: ["3.11", "3.12", "3.13"]
  include:
    - os: macos-latest
      python-version: "3.13"
```

---

### CD-M6: `pip install -e ".[dev]"` in CI uses editable install unnecessarily

**File:** `.github/workflows/ci.yml:29`
**Category:** CI reliability

The CI pipeline uses `pip install -e ".[dev]"` (editable mode). Editable installs are designed for active development and use import hooks or `.pth` files to link to the source tree. In CI, this is unnecessary and can mask packaging issues:

- If the `[tool.hatch.build.targets.wheel]` configuration is wrong (e.g., missing a sub-package), an editable install will still work because it reads directly from the source tree
- A non-editable install (`pip install ".[dev]"`) would catch packaging problems the same way end users would experience them

**Recommendation:** Change to non-editable install in CI:

```yaml
- name: Install dependencies
  run: pip install ".[dev]"
```

Keep editable installs for local development only.

---

## Low

### CD-L1: No `py.typed` marker file

**File:** `pyproject.toml`, package directory
**Category:** Packaging / Type safety
**Cross-ref:** SEC-L3 from Phase 2A

The `pyproject.toml` classifiers include `Typing :: Typed`, but there is no `py.typed` marker file in the `executionkit/` package directory. PEP 561 requires this file for type checkers to recognize the package as typed. Without it, downstream `mypy --strict` users get no type checking on ExecutionKit API calls.

**Recommendation:** Create an empty `executionkit/py.typed` marker file and ensure it is included in the wheel via `pyproject.toml`.

---

### CD-L2: Placeholder URLs in `pyproject.toml`

**File:** `pyproject.toml:47-49`
**Category:** Packaging metadata
**Cross-ref:** SEC-L4 from Phase 2A

```toml
Homepage = "https://github.com/your-org/executionkit"
Issues = "https://github.com/your-org/executionkit/issues"
Changelog = "https://github.com/your-org/executionkit/CHANGELOG.md"
```

These placeholder URLs will appear on PyPI if the package is published. The `your-org` GitHub organization could be claimed by anyone, redirecting users to a malicious repository.

**Recommendation:** Replace with actual repository URLs before the first PyPI publish, or remove the `[project.urls]` section entirely until real URLs are established.

---

### CD-L3: No GitHub Actions cache for pip dependencies

**File:** `.github/workflows/ci.yml`
**Category:** CI performance

The CI pipeline installs dependencies from scratch on every run. For a 6-job matrix, this means 6 independent `pip install` operations downloading the same packages. Adding pip caching would reduce CI runtime and network usage:

```yaml
- name: Set up Python ${{ matrix.python-version }}
  uses: actions/setup-python@v5
  with:
    python-version: ${{ matrix.python-version }}
    cache: 'pip'
```

The `actions/setup-python@v5` has built-in pip caching support. This is a one-line addition.

---

### CD-L4: Publish workflow uses Python 3.11 instead of latest

**File:** `.github/workflows/publish.yml:17-19`
**Category:** Build environment

The publish workflow builds on Python 3.11 while the CI matrix includes 3.11, 3.12, and 3.13. Using the oldest supported version for the build is not inherently wrong (it can catch compatibility issues), but the `build` tool itself may benefit from running on the latest Python. More importantly, this should be a deliberate, documented choice rather than an implicit one.

**Recommendation:** Consider using 3.12 or 3.13 for the build step, or add a comment explaining why 3.11 was chosen.

---

### CD-L5: No branch protection documentation

**File:** `CONTRIBUTING.md`
**Category:** Developer workflow documentation

`CONTRIBUTING.md` describes the PR process (branch naming, one approval required, 400-line limit) but does not document GitHub branch protection settings. There is no mention of:
- Which status checks are required to merge
- Whether force-pushing to `main` is blocked
- Whether the merge queue is enabled
- Whether PRs require up-to-date branches

**Recommendation:** Add a "Branch Protection" subsection to CONTRIBUTING.md describing the expected GitHub settings, or document this in a `docs/development.md` file.

---

## Positive Observations

The following aspects of the CI/CD setup are well-executed and should be preserved:

1. **OIDC Trusted Publishing.** The publish workflow uses `pypa/gh-action-pypi-publish@release/v1` with `permissions: id-token: write` and a dedicated `pypi` environment. This is the most secure PyPI publishing method -- no long-lived API tokens stored as secrets.

2. **Dependabot for both ecosystems.** `.github/dependabot.yml` covers both `pip` and `github-actions` ecosystems with weekly schedules and PR limits. This catches both dependency updates and Actions version bumps.

3. **Comprehensive CI matrix.** Testing across 2 OSes x 3 Python versions (6 combinations) with `fail-fast: false` ensures that a failure on one combination does not hide failures on others.

4. **Coverage enforcement in CI.** `--cov-fail-under=80` in the test step, matching the `pyproject.toml` `[tool.coverage.report]` setting, prevents coverage regression.

5. **Separate security scan job.** Bandit SAST runs as an independent job, keeping security scanning visible and separately reportable.

6. **Build artifact separation.** The publish workflow correctly separates build and publish into distinct jobs, uploading artifacts between them. This is best practice for reproducible releases.

7. **Environment-scoped publishing.** The `pypi` environment on the publish job enables GitHub environment protection rules (approval gates, deployment history).

8. **Pre-commit hooks.** The `.pre-commit-config.yaml` covers linting, formatting, type checking, and secret detection. The `detect-private-key` hook adds a local safety net against credential commits.

9. **Zero runtime dependencies.** From a CI/CD perspective, this is excellent -- no dependency resolution conflicts, no transitive vulnerability surface, fast installs.

10. **Bandit configuration in pyproject.toml.** Bandit skips are documented with inline comments explaining why each rule is suppressed (B101 for asserts, B310 for intentional urllib use, B311 for non-crypto random).

---

## Summary Table

| ID | Severity | Category | File(s) | Description |
|----|----------|----------|---------|-------------|
| CD-H1 | High | Release safety | `publish.yml` | Publish workflow has no CI gate -- can release with failing tests |
| CD-H2 | High | Release integrity | `publish.yml`, `pyproject.toml` | No version-tag consistency check between git tag and package version |
| CD-H3 | High | Tooling drift | `.pre-commit-config.yaml` | Pre-commit hook versions ~10 minor versions behind CI |
| CD-M1 | Medium | Supply chain | `ci.yml` | No dependency vulnerability scanning (pip-audit) in pipeline |
| CD-M2 | Medium | Observability | `ci.yml` | No coverage artifact upload or trend tracking |
| CD-M3 | Medium | Pipeline structure | `ci.yml` | Bandit job isolated; branch protection requirements unclear |
| CD-M4 | Medium | Release docs | `publish.yml` | No changelog verification in release process |
| CD-M5 | Medium | Platform coverage | `ci.yml` | Build matrix missing macOS |
| CD-M6 | Medium | CI reliability | `ci.yml` | Editable install in CI masks packaging issues |
| CD-L1 | Low | Packaging | `pyproject.toml` | No `py.typed` marker file (PEP 561) |
| CD-L2 | Low | Packaging | `pyproject.toml` | Placeholder GitHub URLs could be squatted |
| CD-L3 | Low | CI performance | `ci.yml` | No pip dependency caching |
| CD-L4 | Low | Build environment | `publish.yml` | Publish uses Python 3.11 without rationale |
| CD-L5 | Low | Documentation | `CONTRIBUTING.md` | No branch protection settings documented |

---

## Recommendations Priority

### Immediate (before first PyPI publish)
1. **CD-H1** -- Add CI gate to publish workflow (prevents publishing broken releases)
2. **CD-H2** -- Add version-tag consistency check (prevents version divergence)
3. **CD-L2** -- Replace placeholder URLs in `pyproject.toml` (prevents URL squatting)
4. **CD-L1** -- Add `py.typed` marker file (PEP 561 compliance)

### Short-term (next 2-3 sprints)
5. **CD-H3** -- Update pre-commit hook versions to match CI
6. **CD-M1** -- Add `pip-audit` dependency scanning to CI
7. **CD-M6** -- Switch to non-editable install in CI
8. **CD-M3** -- Document required branch protection status checks
9. **CD-M2** -- Add coverage artifact upload and consider Codecov/Coveralls

### Backlog
10. **CD-M4** -- Add changelog verification to release process
11. **CD-M5** -- Add macOS to build matrix
12. **CD-L3** -- Add pip caching to CI
13. **CD-L4** -- Document Python version choice for publish build
14. **CD-L5** -- Document branch protection settings in CONTRIBUTING.md

---

## Cross-References to Prior Phases

| Prior Finding | CI/CD Impact | Status |
|---------------|-------------|--------|
| SEC-L4 (placeholder URLs) | Publish workflow would push these to PyPI | Confirmed as CD-L2 |
| SEC-L3 (no py.typed) | Published package lacks PEP 561 marker | Confirmed as CD-L1 |
| SEC-L5 (dev dependency pinning) | Dev deps in CI use `>=` bounds; Dependabot mitigates | Partially addressed by Dependabot |
| D-L1 (empty CHANGELOG) | No release process enforces changelog updates | Confirmed as CD-M4 |
| Phase 2A (Bandit configured) | Bandit runs in CI as separate job | Positive; but needs branch protection (CD-M3) |
| Phase 3 (80% coverage gate) | Enforced in CI via `--cov-fail-under=80` | Positive; enhancement via CD-M2 |
