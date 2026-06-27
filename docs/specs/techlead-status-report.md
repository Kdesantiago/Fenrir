# Spec — `/fenrir:status` Tech Lead Report (v2)

- Status: Accepted (v2 — redesigned after `red-team-destroyer` VERDICT: REDESIGN on v1)
- Date: 2026-06-27
- Slug: techlead-status-report
- Origin: `/fenrir:challenge-me "améliore le projet pour être techLead-friendly"`

## Problem

Fenrir is IC/agent-oriented: skills generate, hooks gate. A tech lead has **no surface to
supervise, govern, or onboard onto** the standard. "techLead-friendly" = add that
read/govern layer **in the plugin's grain** (an in-session command + a markdown artifact),
not a web dashboard.

## Users & jobs-to-be-done

- **Adopter lead** — "is this repo *actually* gated (armed), and what's drifting?"
- **Reviewer/approver lead** — "which exceptions are open, lapsed, or self-granted with no
  real approver?"
- **Onboarding lead** — "give a newcomer 'how we deliver here' from the real config."

## Success metric

A lead runs **one command** in a consumer repo and gets a single, **honest** markdown
report — every line either a verified fact or explicitly labeled as unverified/declared —
with zero hand-reading of `.github/`, `org-profile.yaml`, or `gate-exceptions.jsonl`.

## What v1 REJECTS (red-team kill shots — corrected, not papered over)

- **No DORA metrics in v1.** Deploy-freq/lead-time/CFR from local git is a *category error*
  here: tags are SemVer release markers (`release` skill), deploys are in-cluster Argo/
  Flagger reconciles (`progressive-delivery`); `commit→tag` is release-batching latency;
  `fix:`-ratio is commit hygiene, not change-failure. Confident-but-wrong numbers a lead
  would over-trust. **Deferred** until a real deploy-event + incident source exists
  (`incident-runbook`). The report shows *facts* only (last release tag + date), never a
  DORA-shaped metric.
- **No file-presence theater for arming.** "Is this repo gated?" must not be answered by
  `ls branch-protection.tf`. v1 makes ONE live check (below); offline → presence-only,
  explicitly labeled "declared, NOT verified applied".
- **No implied governance the tool can't enforce.** A claimed `approved_by` is unverified
  (no identity/PR link); the report labels it "claimed approver (unverified)".

## Scope (v1 cut — mono-repo, honest signals only)

`commands/status.md` (`/fenrir:status`) runs a deterministic helper and presents a
**Tech Lead Report** for the current repo with three sections:

1. **Gate health (verified where possible)**
   - pre-commit: `.pre-commit-config.yaml` present AND git hooks installed
     (`core.hooksPath`/`.git/hooks/pre-commit`).
   - CI required-checks: GitHub (`.github/workflows/*.yml`) or Azure
     (`azure-pipelines*.yml`) workflow present — labeled "pipeline file present" (names/
     required-status wiring not asserted).
   - **branch-protection — the v1 differentiator:** one live call
     `gh api repos/{owner}/{repo}/branches/{branch}/protection` (Azure: `az repos policy
     list`) → **ARMED / NOT-ARMED (verified)**. With `--offline` (or no `gh`/no auth):
     fall back to `branch-protection.tf` presence, labeled **"declared, NOT verified"**.
   - `template_version` drift: org-profile `template_version` vs installed plugin
     `version`, using the **exact** semver-compat rule from `delivery-gates` (major-match;
     0.x ⇒ minor-match). Pinned by a test to the canonical rule.
2. **Governance / exceptions** — parse `docs/delivery-memory/gate-exceptions.jsonl`:
   list OPEN, non-expired waivers; **flag lapsed-but-open** (past `expires`); **flag
   self-granted** (`approved_by` absent or `== granted_by`) as "claimed approver
   (unverified)".
3. **Onboarding** — "how we deliver here" from `org-profile.yaml` + gate state: declared
   stack, the gate steps, the golden path (`/fenrir:challenge-me` → `/fenrir:deliver` →
   `/fenrir:ship`), and the last release tag + date (a fact, not a metric).

### Governance schema change (memory-keeper) — explicit amendment plan

- Add an OPTIONAL `approved_by` field to the gate-exception schema. A waiver is *approved*
  iff `approved_by` is set and `!= granted_by`; else *self-granted* (flagged, unverified).
- Edits required in `skills/memory-keeper/SKILL.md` (not just "document it"):
  - the schema clause "lines carry all six fields" → "six required + optional `approved_by`".
  - the `waive` step → accept/record `approved_by`.
  - the `expire` step → **name `approved_by` as preserved** on rewrite (so an expire run
    can't strip it).
  - the "field names are fixed / refuses to change schema" guard → carve out the additive
    `approved_by` so the skill isn't self-contradictory.
- Safe for `session-context.py` (reads fixed fields, ignores unknown keys — verified) and
  additive, so existing exception lines keep working.

## Build & CI contract (so "wired into CI" is actually true)

- Helper at **`scripts/techlead_report.py`** (stdlib only). Underscore name so it's
  importable by tests.
- **Extend `.github/workflows/ci.yml`, `pyproject.toml`, and root `.pre-commit-config.yaml`
  to cover `scripts/`** (py_compile + ruff + mypy), and tests at
  **`hooks/tests/test_techlead_report.py`** (collected by the existing `testpaths`).
- Invocation contract: `commands/status.md` runs
  `python3 "$CLAUDE_PLUGIN_ROOT/scripts/techlead_report.py"` against `$CLAUDE_PROJECT_DIR`
  (the consumer repo). `CLAUDE_PLUGIN_ROOT` locates the installed plugin (fallback like
  `delivery-gates`); `CLAUDE_PROJECT_DIR` is the repo under inspection. The `gh`/`az`
  call lives in the helper, gated by `--offline` and a `gh` availability check.

## Acceptance criteria

- `/fenrir:status` command + `scripts/techlead_report.py` (stdlib, **never crashes on a
  partial repo** — missing org-profile / no exceptions file / no `gh` → graceful section +
  exit 0).
- branch-protection: ARMED/NOT-ARMED when `gh` available + authed; "declared, NOT verified"
  offline. Never reports armed from file presence alone.
- Gate-health correct for GitHub and Azure layouts (presence-level, honestly labeled).
- Exceptions: self-granted + lapsed flagged correctly; approved (`approved_by != granted_by`)
  shown as approved (unverified).
- `memory-keeper` SKILL.md amended per the plan above (all four edits).
- Tests in `hooks/tests/` covering: armed-vs-declared gate, GitHub vs Azure, self-granted
  vs approved vs lapsed exception, empty/partial repo, and the semver-compat rule pinned to
  the `delivery-gates` cases. `ruff` + `mypy` + `pytest` green over `hooks/` **and**
  `scripts/`.
- Docs: README "4 commands"→"5" (line 5) + commands table row; PUBLISHING "4 commands"→"5"
  (line 5); CHANGELOG `[Unreleased]`.

## Risks & riskiest assumption

- **Riskiest assumption:** on-disk + one API call is enough signal for the three jobs. True
  for gate-arming (the API call) + exceptions; everything else is labeled declared/
  unverified so it can't create false assurance.
- The live `gh`/`az` call adds an auth/network dependency → MUST degrade gracefully
  (offline label), never block or crash.
- Scope creep back toward fleet/dashboard/DORA — held by "What v1 REJECTS".
