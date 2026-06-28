---
name: simplify
description: Use when reducing code IN PLACE under a behavior-preserving guard (same tests green before AND after) — flatten control flow, delete dead code, inline-away needless indirection, lift a literal to a constant. Split from refactor is mechanical: simplify adds ZERO new named symbols; any move creating a def/class/module (extract, dedup-to-helper) is refactor. Triggers — "flatten this", "make it KISS", "over-engineered", "too many layers". NOT a bug hunt (/code-review), NOT structure-creating moves (refactor), NOT native /simplify. Reads org-profile.yaml `framework`.
---

# Simplify — in-place KISS reduction under a test guard

Make existing code *smaller and plainer in place* without changing what it does and **without creating any new named symbol**. The **green test baseline is the contract**: the SAME tests must pass identically before AND after, so a reduction diff is provably behavior-neutral. The line against `refactor` is mechanical, not a vibe: if the diff adds a `def`/`class`/`function`/new module — extract, dedup-into-a-shared-helper, decompose — that is a structure-creating move and belongs to `refactor` (which owns `extract | inline | rename | move | decompose | dedup-to-helper`). simplify only *deletes* and *rewrites in place*: flatten a branch, drop dead code, inline-away a single-use indirection (removing a symbol, never adding one), pull a repeated literal up to a constant. It does NOT block the merge — the real teeth are the couche-0 CI required-checks + branch-protection (from `repo-bootstrap`), which re-run the same suite at merge time. A skill cannot make anyone run the tests.

## When to use
- "flatten this", "make it KISS", "this is over-engineered", "too many layers/branches here", "drop the dead code", "pull this magic number into a constant"
- You want to *reduce* an existing region in place (fewer branches, fewer lines, no needless indirection) WITHOUT introducing a new function/class/module, while proving behavior did not change
- A pre-merge cleanup pass on top of working, tested code — the org-tier, test-guarded counterpart to the native `/simplify`
- NOTE on the bare word "simplify this": that string also resolves the native `/simplify` quick pass, and trigger time cannot tell them apart — prefer the verbs above ("flatten", "drop dead code") to reach THIS org-tier, test-guarded skill deliberately. If the request is duplication that wants a NEW shared helper, that is `refactor`'s `dedup-to-helper`, not this skill.

## When NOT to use
- Hunting for correctness/security defects in the code → `/code-review` (or `fenrir:security-review`); simplify is quality-only and assumes the code is already correct
- Any transform that CREATES a new named symbol — extract a function/module, fold duplicate blocks into a NEW shared helper (`dedup-to-helper`), rename, move, decompose a god-object → `refactor` (it owns every structure-creating move). The mechanical test: if the diff adds a `def`/`class`/`function`/new file, route to `refactor`; simplify only deletes and rewrites in place.
- A throwaway, unguarded quick pass with no recorded baseline → the native `/simplify` command (this skill is the org-tier, test-guarded version). Be aware the bare phrase "simplify this" can resolve EITHER at trigger time; there is no signal to disambiguate, so invoke this skill by its reduction verbs (flatten / drop dead code / inline-away) when you specifically want the guarded version.
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
3. **Identify the in-place reduction targets.** List ONLY reductions that need no new symbol: over-complex control flow (deep nesting → guard clause / early return / lookup table, redundant branches, boolean gymnastics), needless indirection to *remove* (single-use wrapper or pass-through layer you can inline away — deleting the symbol, not adding one), dead/unreachable code, and a repeated literal you can lift to a single constant. If a target instead wants a NEW shared helper to hold collapsed duplicate logic, STOP and route it to `refactor` (`dedup-to-helper`) — that creates a symbol and is out of scope here.
4. **Apply KISS reductions in SMALL steps.** One reduction per step — replace nested `if/else` with a guard clause / early return / lookup table, inline-away a single-use indirection (removing the wrapper symbol), drop dead code, pull a repeated literal up to a constant. Each step must NET-DELETE structure or hold it flat — never add a `def`/`class`/`function`/module (that is `refactor`). Keep the public surface, side effects, logs, and error paths IDENTICAL. No opportunistic "while I'm here" behavior edits — those are a separate pass (`/fenrir:deliver`).
5. **Re-run tests after EACH step.** Use the SAME command from step 2. Counts must stay IDENTICAL. **Any step that breaks behavior → revert that step** and move on; never rewrite a test to make a reduction pass (rewriting the oracle is an admission behavior changed).
6. **Report the reduction.** Emit what was flattened/deleted/inlined-away, the exact recorded test command + a before/after test-result table (same command, identical counts), and a before/after cyclomatic-complexity delta (`radon cc` count or equivalent) on the touched files. Note deferred items as "deferred" — do not gold-plate. Hand the diff to `reviewer` for merge-readiness.

## Output / validation
- The reduced code (quality-only diff, NO new named symbol) + the recorded test command + a before/after test-result table (SAME command, IDENTICAL pass/fail/skip counts) + a one-line behavior-preservation attestation + a before/after cyclomatic-complexity delta showing the metric measurably dropped.
- Validate: re-running the recorded command yields the recorded counts; `git diff` shows no public-API signature/semantic change, no added `def`/`class`/`function`/module, and no test gained/lost an assertion; the recorded complexity metric is lower than baseline.
- This proves the reduction is behavior-neutral locally; it becomes a gate only once the same suite runs in CI required-checks (couche-0) — not by this skill.

## Refuses when
- `framework` is unset in `org-profile.yaml` (cannot resolve the test runner / guard).
- The baseline is red, or there is no test suite to anchor against — a behavior-preserving reduction cannot be proven (route to a fix / `qa-tester`).
- The requested change alters behavior (new feature, bugfix, changed output/signature semantics) — that is `/fenrir:deliver`, not a simplification.
- The reduction would CREATE a new named symbol (extract a function/module, fold duplicates into a new shared helper, decompose) — that is `refactor`'s charter (`dedup-to-helper` / `extract` / `decompose`), not this skill.
- The diff would add, remove, or rewrite tests to make them pass — simplify re-runs the existing suite unchanged.
- Asked to chase bugs (`/code-review`), make a structure-creating move (`refactor`), or do a quick unguarded pass (native `/simplify`) — route to the owning sibling.
