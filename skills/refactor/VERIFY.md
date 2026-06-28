# VERIFY — refactor

Run after `refactor` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a BEFORE and an AFTER test run are recorded using the SAME command with IDENTICAL pass/fail/skip counts (a green-before, green-after baseline) — the output shows both runs and the command; if they differ, behavior changed
- [ ] `org-profile.yaml` `framework` resolved the test runner actually used: `grep -q '^framework:' org-profile.yaml && echo OK || echo MISSING` and the recorded command matches that framework's runner (pytest / jest / junit / app-test)
- [ ] the diff is structural ONLY — exactly one named transform (extract | inline | rename | move | decompose), no public-signature/semantic/side-effect change, and no test file added, removed, or had an assertion altered: `git diff -- '**/test_*.py' '**/*_test.*' '**/*.spec.*' tests | grep -qE '^[+-]\s*(assert|expect\()' && echo FAIL-TESTS-CHANGED || echo OK` (anchor on real test paths `/tests/|_test\.|\.spec\.`, not the bare `test`/`spec` substring, to avoid false hits on source files like `attestation.py` / `spec_loader.py`)
- [ ] a one-line behavior-preservation attestation is present in the output, and follow-ups (if any) are marked deferred, not done inline

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v pytest` · `command -v jest` (or `npx jest`) · `command -v mvn` · `command -v git` → note absent, don't fail
- [ ] a test suite exists to anchor against (e.g. `tests/`, `*_test.*`, `*.spec.*` present) → note absent, don't fail

## Functional
Check out the pre-refactor commit, run the recorded test command and capture the counts; check out the post-refactor commit and run the SAME command. The two count sets must be identical and both green. Then inspect the diff: it should contain only the named structural transform with no behavioral or test-oracle changes. If the AFTER run shows any new failure or any newly-passing/added test, behavior was not preserved and the refactor must be reverted or flagged.
