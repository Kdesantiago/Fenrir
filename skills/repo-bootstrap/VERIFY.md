# VERIFY — repo-bootstrap

Run after `repo-bootstrap` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] couche-0 smoke test passes end-to-end: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/bootstrap-smoke-test.sh" && echo OK || echo FAIL` (asserts org-profile, all 3 hook types, clean pre-commit, CI↔required-checks coupling, .semgrep.yml, terraform validate)
- [ ] all three pre-commit hook types installed: `for h in pre-commit pre-push commit-msg; do grep -q -- "--hook-type=$h" ".git/hooks/$h" || echo "MISSING $h"; done`
- [ ] CI required-checks + SAST config present: `[ -f .github/workflows/required-checks.yml ] || ls azure-pipeline*.yml >/dev/null 2>&1; [ -f .semgrep.yml ] && echo OK || echo MISSING`
- [ ] agent-side layer wired: `[ -d .claude/hooks ] && [ -f .claude/settings.json ] && [ -d docs/delivery-memory ] && echo OK || echo MISSING`
- [ ] org-profile + branch-protection-as-code emitted: `[ -f org-profile.yaml ] && ls *.tf >/dev/null 2>&1 && echo OK || echo MISSING`
- [ ] CI matches `org-profile.yaml`: GitHub workflow on a GitHub repo XOR Azure pipeline on an Azure repo — no wrong-CI artifact, no second weaker pipeline added

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v pre-commit` · `command -v gitleaks` · `command -v terraform` · `command -v gh` → note absent, don't fail (gate only goes live after `terraform apply`)

## Functional
- `pre-commit run --all-files` exits 0 on the bootstrapped tree, and the CI job names equal the branch-protection `required_checks` (the smoke test's step [4/6] asserts this coupling).
