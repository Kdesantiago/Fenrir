# VERIFY — simplify

Run after `simplify` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a `framework` is declared so the test-guard runner is resolvable: `grep -qE '^framework:\s*\S+' org-profile.yaml && echo OK || echo MISSING`
- [ ] a test suite exists to anchor the guard (no preservation proof without it): `{ ls tests >/dev/null 2>&1 || ls **/tests >/dev/null 2>&1 || ls **/test_*.py >/dev/null 2>&1 || ls **/*.test.* >/dev/null 2>&1; } && echo OK || echo MISSING`
- [ ] the BEFORE baseline was recorded GREEN and the AFTER run uses the SAME command with IDENTICAL pass/fail/skip counts (a before/after test-result table is in the output) — a red baseline or any count change is a failure
- [ ] no behavior/public-API change: `git diff` shows no changed function signature semantics, side effect, log, or error path beyond the reduction — and NO test file gained or lost an assertion: `git diff -- '**/test_*.py' '**/*.test.*' tests | grep -qE '^[+-]\s*(assert|expect\()' && echo CHANGED-TESTS-REVIEW || echo OK`
- [ ] duplication/complexity is MEASURABLY lower: the report carries a before/after LOC + complexity delta (e.g. `radon cc` count or duplicate-block count) that decreased — not just a prose claim
- [ ] scope is quality-only: no bug-fix, no structural move/rename (that is `refactor`), no rule-tier change (that is `quality-master`) folded into this diff

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v pytest` · `command -v radon` (complexity delta) · `command -v jscpd` (copy/paste detector) · `command -v git` → note absent, don't fail

## Functional
- Re-run the recorded test command against the reduced code and confirm it yields the recorded GREEN counts (the same pass/fail/skip as the BEFORE baseline), proving the DRY/KISS reduction is behavior-neutral; then re-measure LOC/cyclomatic complexity (or duplicate-block count) on the touched files and confirm the metric is below the baseline recorded in the report.
