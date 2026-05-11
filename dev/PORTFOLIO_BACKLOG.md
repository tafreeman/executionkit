# ExecutionKit — Portfolio Signal Backlog

> **Purpose:** This backlog targets *hiring-panel perception* of the repo, not library
> functionality. Items come directly from the 2026-05-11 four-lens portfolio review.
> Do not conflate with `dev/BACKLOG.md` (library feature work).
>
> **Audience:** Solo candidate; estimated velocity 10–12 story points per sprint
> (part-time, ~3–5 focused hours/week on portfolio work).
>
> **Ratings:**
> - **Impact** (1–5): Portfolio signal value to a director-level reviewer in a 15-minute scan.
>   5 = eliminates a Critical/High risk or adds a principal-grade artifact.
> - **Complexity** (1–5): Effort and judgment required.
>   1 = under 30 min, 2 = 1–2 hr, 3 = half day, 5 = full day, 8 = 2–3 days.
> - **Story Points (SP):** Fibonacci sizing for sprint planning.
> - **Priority Score:** Impact ÷ Complexity (higher = do sooner).

---

## Rating Legend

| Impact | Meaning |
|--------|---------|
| 5 | Eliminates a Critical anti-signal OR adds a principal-level artifact |
| 4 | Directly improves a High-risk item or adds clear differentiation |
| 3 | Medium portfolio improvement; expected baseline for a library |
| 2 | Minor polish; most reviewers won't notice either way |
| 1 | Cosmetic only |

| Complexity | Meaning |
|------------|---------|
| 1 | Under 30 min — mechanical, no judgment required |
| 2 | 1–2 hours — some decisions but well-defined |
| 3 | Half day — requires research or careful writing |
| 5 | Full day — architecture, new systems |
| 8 | 2–3 days — meaningful build work |

---

## Full Backlog

| ID | Item | Source | Impact | Complexity | SP | Priority Score | Sprint |
|----|------|--------|--------|------------|----|----------------|--------|
| PB-01 | Delete raw AI session transcripts from repo | Risk 1 / Quick Win 1 | 5 | 1 | 1 | 5.0 | S1 |
| PB-02 | Write 3 ADRs (structural protocols, flat layout, single provider) | Risk 3 / Quick Win 2 | 5 | 2 | 3 | 2.5 | S2 |
| PB-03 | Add `PORTFOLIO.md` root-level orientation guide | Quick Win 4 | 4 | 1 | 1 | 4.0 | S1 |
| PB-04 | Strip 57 redundant `@pytest.mark.asyncio` decorators | Risk 4 / Quick Win 3 | 2 | 1 | 1 | 2.0 | S1 |
| PB-05 | README: add "For Reviewers" nav section surfacing arch.md + ADRs | Lens 3 / Landing Page | 3 | 1 | 1 | 3.0 | S1 |
| PB-06 | Restructure `dev/planning/` — archive historical AI artifacts, move to `docs/` | Risk 1 / Anti-Signal | 4 | 2 | 2 | 2.0 | S1 |
| PB-07 | Relocate or gitignore `.full-review/` machine-generated state files | Anti-Signal | 3 | 1 | 1 | 3.0 | S1 |
| PB-08 | Add `uv.lock` (or `requirements.lock`) + `pip-audit` step to CI | Risk 5 / Gap 4 | 3 | 1 | 1 | 3.0 | S2 |
| PB-09 | Add CodeQL (or Semgrep) SAST job to CI alongside Bandit | Gap 4 / Supply chain | 3 | 2 | 2 | 1.5 | S2 |
| PB-10 | Generate and commit SBOM (`cyclonedx-bom` or `pip-sbom`) | Gap 4 / OWASP SCVS C-9.1 | 3 | 2 | 2 | 1.5 | S2 |
| PB-11 | Add OIDC Trusted Publishing to `publish.yml` (replace classic token) | Gap 4 / SLSA L1 | 3 | 2 | 2 | 1.5 | S2 |
| PB-12 | Minimal LLM eval harness: Promptfoo or custom deterministic eval in CI | Risk 2 / Gap 1 / MLOps L2 | 5 | 5 | 8 | 1.0 | S3 |
| PB-13 | OTel pluggable tracing hook on `PatternResult` + example Langfuse export | Gap 2 / Google SRE | 4 | 5 | 8 | 0.8 | S3 |
| PB-14 | Federal/regulated readiness: ADR + notes on CUI handling, air-gap path, audit trail | Gap 3 / NIST RMF | 4 | 3 | 5 | 1.3 | S3 |
| PB-15 | Fix `examples/` excluded from `mypy --strict` (implicit type gap) | Lens 1 / Tooling | 2 | 2 | 2 | 1.0 | S2 |
| PB-16 | Cross-stack work: TypeScript usage example or simple HTML demo tool interface | Gap 5 / Breadth | 3 | 8 | 13 | 0.4 | S4 |

---

## Sprint Plans

> Capacity: ~10–12 SP per sprint (3–5 focused hours/week on portfolio work).
> Sprints are thematic — each has a reviewable state by end.

---

### Sprint 1 — "Stop the Bleeding"
**Goal:** A director landing on this repo today sees no anti-signals in the first 15 minutes.
**Capacity:** 7 SP | **Load:** 7 SP (100%)

| ID | Item | SP | Notes |
|----|------|----|-------|
| PB-01 | Delete raw AI transcripts (`convo.txt`, `chatgpt covo.txt`, `.docx`, `.pdf`) | 1 | `git rm` + update `.gitignore`. Check no other files in dev/planning/ are still raw logs. |
| PB-03 | Add `PORTFOLIO.md` at repo root | 1 | 3 paragraphs: what this repo is, what to read first (arch.md, CONTRIBUTING.md Anti-Scope, examples/), relationship to agentic-runtimes. |
| PB-04 | Strip 57 redundant `@pytest.mark.asyncio` decorators | 1 | `asyncio_mode = "auto"` makes them no-ops. `grep -rn "@pytest.mark.asyncio" tests/` then surgical delete. CI must still pass. |
| PB-05 | README "For Reviewers" section | 1 | Below badges, before Quick Start. Two links: `docs/architecture.md`, `CONTRIBUTING.md#anti-scope`. One sentence framing the 2-tier stack. |
| PB-06 | Archive `dev/planning/` AI planning artifacts | 2 | Move to `docs/planning/` with a header marking them historical. Delete raw logs (PB-01 covers the worst offenders). Keep FINAL_VERDICT.md, SHIP_DECISION.md as decision context — they'll become source material for PB-02 ADRs. |
| PB-07 | Relocate `.full-review/` state files | 1 | Move to `docs/review-process/` or add `state.json` to `.gitignore`. The playbooks (`01-quality-architecture.md` etc.) can stay in `docs/review-process/` as methodology documentation. |

**Definition of Done:**
- [ ] No raw AI conversation transcripts on `main`
- [ ] `PORTFOLIO.md` exists at root and links to 3 key artifacts
- [ ] `pytest` green with redundant marks stripped
- [ ] README "For Reviewers" section visible above the fold on GitHub

---

### Sprint 2 — "Build the Signal"
**Goal:** Principal-grade artifacts are now discoverable and supply-chain posture is documented.
**Capacity:** 12 SP | **Load:** 12 SP (100%)

| ID | Item | SP | Notes |
|----|------|----|-------|
| PB-02 | Write 3 ADRs | 3 | Use [MADR template](https://adr.github.io/madr/). Create `docs/adr/README.md` index. **ADR-001:** Structural protocols over ABC (pull rationale from `dev/planning/FINAL_VERDICT.md`). **ADR-002:** Flat layout over src/ (documented in `docs/architecture.md:11-12`). **ADR-003:** Single OpenAI-compatible provider vs. native adapter matrix (pull from `dev/BUILD_SPEC.md` Anti-Scope section). |
| PB-08 | Add lockfile + pip-audit to CI | 1 | `pip install uv && uv pip compile pyproject.toml --extra dev -o requirements.lock`. Add `pip-audit` step after Bandit job in `ci.yml`. Commit `requirements.lock`. |
| PB-09 | Add CodeQL SAST job to CI | 2 | GitHub provides CodeQL Actions for free on public repos. Add `.github/workflows/codeql.yml` with Python language config. Alternatively add a `semgrep --config=auto` step to existing `ci.yml`. |
| PB-10 | Generate and commit SBOM | 2 | `pip install cyclonedx-bom && cyclonedx-py -p -o sbom.json`. Add `sbom.json` to repo root. Add generation step to `publish.yml` so it regenerates on each release. |
| PB-11 | OIDC Trusted Publishing in `publish.yml` | 2 | Replace `PYPI_API_TOKEN` secret with PyPA OIDC trusted publisher. Update workflow to use `pypa/gh-action-pypi-publish@release/v1` with `id-token: write` permission. Register the trusted publisher on PyPI. |
| PB-15 | Fix `examples/` mypy exclusion | 2 | Remove `examples/` from `[tool.mypy] exclude` in `pyproject.toml`. Fix any type errors in `examples/*.py`. Users copy-paste examples — they should be typed. |

**Definition of Done:**
- [ ] 3 ADRs committed under `docs/adr/` with `docs/adr/README.md` index
- [ ] `requirements.lock` present and CI installs from it
- [ ] CodeQL or Semgrep running in CI with no critical findings
- [ ] `sbom.json` present at root, regenerated by `publish.yml`
- [ ] `examples/*.py` passes `mypy --strict`

---

### Sprint 3 — "Demonstrate Depth"
**Goal:** The repo shows production-readiness thinking a GenAI delivery lead is expected to have: eval gates and observability hooks.
**Capacity:** 13 SP | **Load:** 13 SP (100%)

| ID | Item | SP | Notes |
|----|------|----|-------|
| PB-12 | Minimal LLM eval harness in CI | 8 | **Option A (Promptfoo):** Add `evals/promptfoo.yaml` with 3–5 deterministic test cases against `MockProvider`. Add `promptfoo eval` step to CI that fails on regression. **Option B (custom):** Add `evals/eval_consensus.py` that runs consensus against a fixed `MockProvider` fixture, asserts `agreement_ratio >= 0.6`, and returns non-zero exit on failure. Add as a CI step. Either approach produces the artifact; Option B requires no new tooling dep. Document in `docs/evals/README.md` why this exists and what it gates. |
| PB-13 | OTel pluggable tracing hook | 8 | Add an optional `tracer: opentelemetry.trace.Tracer | None = None` parameter to `consensus`, `refine_loop`, `react_loop`. When non-None, wrap each `checked_complete` call in a span with attributes: `pattern.name`, `pattern.iteration`, `llm.model`, `llm.input_tokens`, `llm.output_tokens`. Gate behind `TYPE_CHECKING` import so OTel is not a hard dep. Add `executionkit[otel]` optional extra. Add an example `examples/otel_tracing.py` exporting to stdout. This directly answers "how do you monitor this in production?" |
| PB-14 | Federal/regulated readiness documentation | 5 | **ADR-004:** Data residency and air-gap deployment (Ollama path enables air-gapped use; document CUI-scope guidance for self-hosted models). Add `docs/federal-deployment.md`: covers local-only model path, no-phone-home guarantee (stdlib urllib, no telemetry), audit trail pattern using `PatternResult.cost` as an immutable call record, credential isolation (env vars, no logging). Not a security claim — a deployment guide for regulated environments. Cross-link from `SECURITY.md`. |

**Definition of Done:**
- [ ] `evals/` directory exists with at least 3 deterministic test cases
- [ ] Eval step runs in CI and blocks merge on regression
- [ ] OTel hook implemented with `examples/otel_tracing.py`
- [ ] `docs/federal-deployment.md` committed and cross-linked from `SECURITY.md` and `README.md`
- [ ] ADR-004 committed

---

### Sprint 4 — "Strategic Differentiation"
**Goal:** Breadth signal for a delivery lead role: the portfolio shows more than one language/stack.
**Capacity:** 13 SP | **Load:** 13 SP (100%)

| ID | Item | SP | Notes |
|----|------|----|-------|
| PB-16 | Cross-stack work: TypeScript or HTML | 13 | **Recommended path:** Add `examples/browser-demo/` — a single-file HTML + vanilla JS interface that calls a local Ollama instance via the same OpenAI-compatible endpoint ExecutionKit uses. No build step, no framework. Shows: (1) ability to work across the stack, (2) understanding that the library's provider protocol maps directly to a browser fetch, (3) practical zero-dependency design thinking carried into a second language. Alternatively, add a TypeScript wrapper `examples/ts-client/index.ts` demonstrating how to call an OpenAI-compatible endpoint and consume a `PatternResult`-shaped response. Add a top-level note in `README.md` linking to it. |

**Definition of Done:**
- [ ] `examples/browser-demo/` or `examples/ts-client/` committed and documented
- [ ] Referenced from `README.md`
- [ ] Works against local Ollama with no API key

---

## Dependency Graph

```
PB-01 (delete transcripts)
  └── PB-06 (archive planning/) — do PB-01 first, then restructure

PB-02 (ADRs)
  └── PB-06 (archive planning/) — ADRs pull content from planning docs; archive after extraction

PB-08 (lockfile)
  └── PB-09 (CodeQL) — independent, but batch into same CI PR
  └── PB-10 (SBOM)
  └── PB-11 (OIDC publish)

PB-12 (eval harness) — independent; no blocking deps
PB-13 (OTel hooks) — independent; no blocking deps
PB-14 (federal docs) — independent; no blocking deps

PB-15 (examples/ mypy) — must come before PB-16 (cross-stack work)
  └── PB-16 (cross-stack work)
```

Items within each sprint are independent and can be batched into a single PR per sprint,
except where the dependency graph requires sequencing within a sprint.

---

## Backlog Items Not Scheduled (Parking Lot)

These have real value but are deferred past Sprint 4 due to complexity or diminishing return
at this portfolio stage.

| ID | Item | Reason deferred |
|----|------|-----------------|
| PL-01 | Sigstore/cosign artifact signing on PyPI releases | SLSA L2+; low ROI for a v0.1 alpha with limited external consumers |
| PL-02 | Promptfoo full regression suite with golden outputs | Requires stable prompt templates; premature before v0.2 pattern set |
| PL-03 | Structured logging (`structlog`) replacing `logging` module | Architecture change; low reviewer impact relative to effort |
| PL-04 | GitHub issue templates and PR template | Good practice, not a 15-minute-scan signal |
| PL-05 | Streaming provider support | Scoped to v0.2 per `dev/BUILD_SPEC.md`; adding it here breaks scope discipline |

---

## Metrics to Track Progress

Run these at the start of each sprint to confirm direction:

```bash
# Confirm no raw logs remain
find dev/ -name "*.txt" -o -name "convo*" | wc -l   # target: 0

# Confirm ADRs exist
ls docs/adr/*.md | wc -l                              # target: >= 3 after Sprint 2

# Confirm asyncio marks stripped
grep -r "@pytest.mark.asyncio" tests/ | wc -l         # target: 0 after Sprint 1

# Confirm lockfile present
ls requirements.lock                                   # target: exists after Sprint 2

# Confirm eval harness runs
python evals/eval_consensus.py && echo "PASS"          # target: exits 0 after Sprint 3

# Confirm SBOM present
ls sbom.json                                           # target: exists after Sprint 2
```
