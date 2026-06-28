# VERIFY — simplify

Run after `simplify` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (machine-checkable; the skill's output is incomplete/wrong if any fail)
- [ ] a `framework` is declared so the test-guard runner is resolvable: `grep -qE '^framework:\s*\S+' org-profile.yaml && echo OK || echo MISSING`
- [ ] NO test file gained or lost an assertion (rewriting the oracle = behavior changed) — this command FAILS non-zero on any assertion delta: `! git diff -- '**/test_*.py' '**/*_test.*' '**/*.spec.*' tests | grep -qE '^[+-]\s*(assert|expect\()'` (anchor on real test paths `/tests/|_test\.|\.spec\.`, not the bare `test`/`spec` substring, to avoid false hits on source files like `attestation.py` / `spec_loader.py`)
- [ ] the diff CREATES no new named symbol (extract / dedup-to-helper / decompose are `refactor`, not simplify) — this command FAILS non-zero if a `def`/`class`/`function` was added: `! git diff | grep -qE '^\+\s*(def |class |function |[A-Za-z0-9_]+\s*=\s*function|export (default )?(function|class))'`

## Informational (NOT machine-verifiable here / tooling presence — note, do NOT block)
- [ ] the BEFORE baseline was recorded GREEN and the AFTER run uses the SAME command with IDENTICAL pass/fail/skip counts (a before/after test-result table is in the output) — self-attested in the report; the actual re-run lives in Functional below, a count change there is the real failure
- [ ] no changed function-signature semantics, side effect, log, or error path beyond the reduction — human prose, no command can evaluate "semantics"; reviewer eyeballs the diff
- [ ] complexity is lower — the report carries a before/after cyclomatic delta; the numeric proof is computed in Functional (not self-attestation)
- [ ] scope is quality-only: no bug-fix, no rule-tier change (`quality-master`) folded in — reviewer judgement, not a grep
- [ ] a test suite exists to anchor the guard: `{ ls tests >/dev/null 2>&1 || ls **/test_*.py >/dev/null 2>&1 || ls **/*.test.* >/dev/null 2>&1; } && echo PRESENT || echo ABSENT`
- [ ] `command -v pytest` · `command -v radon` (cyclomatic delta) · `command -v jscpd` (copy/paste detector) · `command -v git` → note absent, don't fail

## Functional (the real, machine-checked guard — run, do not self-attest)
- Parse the test command recorded in the report, check out the pre-simplify commit, run it and capture the pass/fail/skip counts; check out the post-simplify commit and run the SAME command. The two count sets MUST be identical and both GREEN — any new failure or any newly-passing/added test means behavior was not preserved → revert.
- Compute the complexity delta numerically, do not trust the report's table: `radon cc -s -a <touched files>` on the pre-simplify commit vs the post-simplify commit (or `jscpd` duplicate-block count) and assert the post value is strictly lower than the pre value. If it is not below baseline, the reduction did not actually reduce — fail.
