---
name: quality-master
description: Use when you want to RAISE the quality bar to the expert/strict tier — strict mypy, a broad ruff ruleset, and an expert pytest strategy (fixtures, parametrize, Hypothesis property tests, coverage targets, markers). NOT for running existing tooling on a diff (delivery-gates), NOT for basic init config (repo-bootstrap). Configures the strict tier and ratchets settings UP only. Reads org-profile.yaml framework and refuses without it.
---

# Quality Master — the strict tier

This skill **raises** the quality bar; it does not enforce it. The real gate is couche-0 (CI required-checks + branch-protection from `repo-bootstrap`); these configs only make that gate stricter once they're committed. A skill cannot make anyone run them.

## When to use
- "make the linting/types/tests strict", "configure the expert quality tier", "tighten mypy/ruff/pytest"
- You already have basic config (from `repo-bootstrap`) and want the comprehensive, opinionated ruleset on top

## When NOT to use
- Running lint/type/test on a working diff for fast feedback → `delivery-gates`
- First-time repo init / basic tool config + hooks/CI → `repo-bootstrap`
- SAST/SBOM/threat-check → `security-review`
- No declared framework → this skill refuses

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED (selects test idioms: fastapi → `TestClient`/async fixtures; streamlit → app-test harness; etc.)
- The repo's EXISTING mypy/ruff/pytest config — read first; this skill only ratchets up, never down

## Steps
1. Read `org-profile.yaml`; resolve `framework`. If unset, REFUSE.
2. Read existing `pyproject.toml` / `mypy.ini` / `ruff.toml` / `pytest.ini`. Record every current setting. Verify rule codes/options against current mypy, ruff, pytest, and Hypothesis docs before writing (rule sets and flags change between releases — note this in the PR).
3. **mypy → strict.** Set `strict = true` and assert its components are on: `disallow_untyped_defs`, `warn_return_any`, `no_implicit_optional`, `warn_unused_ignores` (plus `disallow_any_generics`, `check_untyped_defs`). If a setting is ALREADY stricter than the target, KEEP it — do not loosen.
4. **ruff → comprehensive.** Broaden `select` (e.g. `E,F,W,I,N,UP,B,C4,SIM,ARG,PTH,RUF` + framework-relevant groups). Every relaxation goes in `per-file-ignores` with a one-line justification comment (e.g. tests may allow `S101`/`ARG`; `__init__.py` may allow `F401`). No blanket `ignore` without a reason.
5. **pytest → expert strategy.** Configure: shared `fixtures` (conftest), `@pytest.mark.parametrize` for all input/edge cases, property-based tests with **Hypothesis** for invariants, per-package coverage targets (`--cov` with a fail-under per package), and markers `unit | integration | e2e` registered in config (`-m` selectable, `--strict-markers`). Guidance: cover every PUBLIC function + its edge cases (empty, boundary, error, unicode).
6. Emit a **test plan** mapping the public surface → required tests (function → unit/parametrize cases, invariants → Hypothesis properties, flows → integration/e2e), so coverage targets are met by design, not by accident.

## Output / validation
- Strict `mypy` + comprehensive `ruff` + expert `pytest` config (merged into `pyproject.toml` or the repo's existing files)
- A test-plan doc mapping public surface → tests with the markers and per-package coverage targets
- Validate: `mypy` runs clean under strict (or lists honest debt), `ruff check` passes with only justified ignores, `pytest -m unit` selects correctly and coverage fail-under is wired
- These configs become teeth only once committed and run by CI (couche-0) — not by this skill

## Refuses when
- `framework` is unset in `org-profile.yaml`
- Asked to LOWER an existing stricter setting — this skill ratchets up only; report the conflict and stop
