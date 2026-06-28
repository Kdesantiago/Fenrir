---
name: refactor
description: Use when restructuring code WITHOUT changing behavior — extract, rename, move, decompose a god-object. Pins a GREEN test baseline, applies the smallest mechanical diff, asserts the SAME tests pass after. Triggers — "refactor this", "extract/rename/move/decompose", "clean up without changing behavior". NOT for design (architect/ADR), NOT for behavior-changing feature/bugfix (/fenrir:deliver), NOT for perf work (fenrir:optimize), NOT for DRY/KISS reduction (fenrir:simplify). Reads org-profile.yaml `framework`; refuses on a red baseline. Advisory — CI is the real gate.
---

# Refactor — behavior-preserving restructuring

Restructure for clarity, not behavior. The **green test baseline is the contract**: the SAME tests must pass identically before and after, so a structural diff is provably behavior-neutral. The skill records the before/after runs and attests the delta is zero; it does NOT block the merge — the real teeth are the couche-0 CI required-checks + branch-protection, which run the same suite at merge time. A skill cannot make anyone run the tests.

## When to use
- "refactor this", "extract this into a function/module", "rename X everywhere", "split this god-class", "decompose this", "untangle the structure (move/extract)", "restructure this without changing behavior"
- You want to restructure for clarity/maintainability and need a guarantee behavior did not change
- Pre-work hygiene before a feature lands on top of messy code (separate the restructure from the change)

## When NOT to use
- A refactor that is really a DESIGN choice (which pattern, which boundary, which abstraction) → `architect` decides and writes an ADR; this skill executes a mechanical transform, it does not pick the target design
- Any change that alters behavior — feature, bugfix, new output → `/fenrir:deliver` (a refactor that changes a test is not a refactor)
- Pure quality/dedup cleanup with no structural move and no before-baseline contract → `fenrir:simplify` (the native `/simplify` applies cleanups; refactor pins a recorded green baseline and attests no delta)
- Performance/throughput/latency work (which legitimately changes behavior characteristics) → `fenrir:optimize`
- Merge-readiness / correctness review of the resulting diff → `reviewer` (the agent; it FLAGS, refactor produces the change); SAST on the diff → `fenrir:security-review`
- No test suite to anchor preservation against → refuse and route to `qa-tester` first (cannot prove preservation with nothing to re-run)

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED; selects the test runner: `fastapi`/`fastapi-sqlalchemy` → `pytest`, `streamlit` → app-test harness (`pytest` + `streamlit.testing`), `express` → `jest`/`vitest`, `spring` → `junit`/`mvn test`. If unset, REFUSE.
- The target code region/files + the transform requested (extract | inline | rename | move | decompose)
- The repo's EXISTING test suite — this is the baseline. Refactor never authors new behavior tests (that is `qa-tester`); it only re-runs what is already green.

## Steps
1. **Resolve the runner.** Read `org-profile.yaml`; map `framework` → the exact test command (e.g. `pytest -q`, `npx jest`, `mvn -q test`). If `framework` is unset, REFUSE — the runner is unknown.
2. **Pin the BEFORE baseline.** Run the full (or tightly scoped, but documented) suite. Record the exact command and the pass/fail/skip counts. **If ANY test is red, STOP** — you cannot prove preservation against a red baseline. Route to a fix or to `qa-tester`, do not proceed.
3. **Name the transform + scope.** State exactly ONE transform class for this pass — `extract` | `inline` | `rename` | `move` | `decompose` — and its concrete scope (files, symbols, call sites). One transform class per pass keeps the diff reviewable; mixing them defeats the proof. (Collapsing duplication into a shared helper is `fenrir:simplify`'s charter, not refactor's.)
4. **Apply the smallest mechanical diff.** Make only the structural change. Do NOT add, remove, or alter any behavior, public-signature semantics, side effect, log, or error path. A signature-changing move (e.g. extracted helper) must leave every call site behavior-identical. No opportunistic "while I'm here" edits — those are a separate pass.
5. **Pin the AFTER baseline.** Re-run with the **SAME command** from step 2. Assert pass/fail/skip counts are IDENTICAL to BEFORE. A new failure means behavior broke → revert. A newly passing or newly added test means behavior changed → revert or flag (that is not a refactor).
6. **Attest + hand off.** Emit a before/after test-result table and a one-line behavior-preservation attestation. Note follow-ups as "deferred" (do not gold-plate). Hand the diff to `reviewer` for the merge-readiness check.

## Output / validation
- The restructured code (structural diff only) + a before/after test-result table showing the SAME command and IDENTICAL counts + a one-line behavior-preservation attestation.
- Validate: re-running the recorded command yields the recorded counts; `git diff` shows no public-API signature/semantic change beyond the named transform; no test file gained or lost an assertion.
- This proves the delta is zero locally; it becomes a gate only once the same suite runs in CI required-checks (couche-0) — not by this skill.

## Refuses when
- `framework` is unset in `org-profile.yaml` (cannot resolve the test runner).
- The BEFORE baseline is red, or there is no test suite to run — preservation cannot be proven (route to a fix / `qa-tester`).
- The requested change alters behavior (new feature, bugfix, changed output/signature semantics) — that is `/fenrir:deliver`, not a refactor.
- The diff would add, remove, or rewrite tests to make them pass — refactor re-runs the existing suite unchanged; rewriting the oracle is an admission behavior changed.
