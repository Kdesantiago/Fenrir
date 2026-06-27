# VERIFY — security-review

Run after `security-review` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the native `/security-review` actually ran over the working diff (no diff arg passed) and its findings are folded into the report — or, if the command is absent, the report says so plainly and a manual threat-check of the changed paths was done (no false claim a tool ran)
- [ ] each finding carries severity + `file:line` + a concrete remediation, and a dependency/SBOM delta is included for the lockfiles touched by the diff
- [ ] NO secrets are reported here (out of scope — that is the gitleaks pre-commit hook); a secret finding means the skill overstepped its boundary

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v semgrep` · `command -v syft` (or the repo's SBOM tool) → note absent, don't fail
- [ ] native `/security-review` command available in the environment → note absent and fall back to manual threat-check

## Functional
- Re-run `/security-review` on the same diff; the findings must be reproducible (same severity-ranked set, same file:line locations).
