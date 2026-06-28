---
name: simplify
description: Use when reducing code to DRY + KISS — collapse duplication, flatten needless abstraction/indirection, simplify control flow — under a recorded behavior-preserving guard (tests green before AND after). Triggers — "simplify this", "make it DRY", "remove duplication", "this is over-engineered". NOT a bug hunt (/code-review), NOT a structural move/rename (refactor — that moves structure, simplify reduces it), NOT the native /simplify quick pass — this is the org-tier, test-guarded version tied to quality-master and data-model. Reads org-profile.yaml `framework`.
---

# Simplify — DRY + KISS under a test guard

Make the code *smaller and plainer* without changing what it does. The **green test baseline is the contract**: the SAME tests must pass identically before AND after, so a reduction diff is provably behavior-neutral. This skill collapses duplication and flattens needless abstraction; it does NOT block the merge — the real teeth are the couche-0 CI required-checks + branch-protection (from `repo-bootstrap`), which re-run the same suite at merge time. A skill cannot make anyone run the tests.

## When to use
- "simplify this", "make it DRY/KISS", "remove the duplication", "this is over-engineered", "flatten this", "too many layers here"
- You want to *reduce* code volume/complexity (fewer lines, fewer branches, fewer abstractions) while proving behavior did not change
- A pre-merge cleanup pass on top of working, tested code — the org-tier, codemod-style version of a quick cleanup

## When NOT to use
- Hunting for correctness/security defects in the code → `/code-review` (or `fenrir:security-review`); simplify is quality-only and assumes the code is already correct
- A behavior-preserving structural MOVE — extract, rename, move, decompose a god-object → `refactor` (it pins a baseline and *moves* structure; simplify *reduces* it — different transform class)
- A throwaway, unguarded quick pass with no recorded baseline → the native `/simplify` command (this skill is the org-tier, test-guarded version)
- Raising the strict lint/type/test tier itself → `quality-master` (simplify reduces code; quality-master ratchets the rules up)
- Schema/index/query-shape reduction (N+1, query layer) → `data-model` (it owns the ORM/query layer)
- Performance/latency work that changes behavior characteristics → `fenrir:optimize`

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED; selects the test runner + idioms: `fastapi`/`fastapi-sqlalchemy` → `pytest -q`, `streamlit` → `pytest` + `streamlit.testing`, `express` → `jest`/`vitest`, `spring` → `junit`/`mvn -q test`. If unset, REFUSE — the guard's runner is unknown.
- The target files/dir to simplify (the scope of the reduction pass)
- The repo's EXISTING test suite — this is the guard. Simplify never authors new behavior tests (that is `qa-tester`); it only re-runs what is already green.

## Steps
1. **Resolve the runner.** Read `org-profile.yaml`; map `framework` → the exact test command. If `framework` is unset, REFUSE.
2. **Record a GREEN baseline.** Run the full (or tightly-scoped, but documented) suite. Record the exact command + pass/fail/skip counts. **If ANY test is red, STOP** — you cannot prove a reduction is behavior-neutral against a red baseline. Route to a fix or to `qa-tester`.
3. **Identify the reduction targets.** Apply the **rule of three** for duplication (two copies may stay; three is a DRY candidate). List: duplicated blocks/literals, needless indirection (single-use wrappers, pass-through layers, premature interfaces), and over-complex control flow (deep nesting, redundant branches, boolean gymnastics). Distinguish *incidental* duplication (collapse) from *coincidental* similarity (leave — collapsing it couples unrelated code).
4. **Apply DRY/KISS transforms in SMALL steps.** One reduction per step — e.g. extract a repeated literal to a constant, fold three copies into one helper, inline a single-use indirection, replace nested `if/else` with a guard clause / early return / lookup table, drop dead code. Keep the public surface, side effects, logs, and error paths IDENTICAL. No opportunistic "while I'm here" behavior edits — those are a separate pass (`/fenrir:deliver`).
5. **Re-run tests after EACH step.** Use the SAME command from step 2. Counts must stay IDENTICAL. **Any step that breaks behavior → revert that step** and move on; never rewrite a test to make a reduction pass (rewriting the oracle is an admission behavior changed).
6. **Report the reduction.** Emit what was collapsed/flattened, a before/after test-result table (same command, identical counts), and before/after LOC + a complexity delta (e.g. `radon cc` / cyclomatic count, or duplicate-block count). Note deferred items as "deferred" — do not gold-plate. Hand the diff to `reviewer` for merge-readiness.

## Output / validation
- The reduced code (quality-only diff) + a before/after test-result table (SAME command, IDENTICAL pass/fail/skip counts) + a one-line behavior-preservation attestation + a before/after LOC and complexity delta showing duplication measurably dropped.
- Validate: re-running the recorded command yields the recorded counts; `git diff` shows no public-API signature/semantic change and no test gained/lost an assertion; the complexity/duplication metric is lower than baseline.
- This proves the reduction is behavior-neutral locally; it becomes a gate only once the same suite runs in CI required-checks (couche-0) — not by this skill.

## Refuses when
- `framework` is unset in `org-profile.yaml` (cannot resolve the test runner / guard).
- The baseline is red, or there is no test suite to anchor against — a behavior-preserving reduction cannot be proven (route to a fix / `qa-tester`).
- The requested change alters behavior (new feature, bugfix, changed output/signature semantics) — that is `/fenrir:deliver`, not a simplification.
- The diff would add, remove, or rewrite tests to make them pass — simplify re-runs the existing suite unchanged.
- Asked to chase bugs (`/code-review`), move/rename structure (`refactor`), or do a quick unguarded pass (native `/simplify`) — route to the owning sibling.
