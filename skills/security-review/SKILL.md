---
name: security-review
description: Use when you want SAST + dependency/SBOM + threat-check on a git diff via the native /security-review command. Triggers — "security review my changes", "run SAST on this diff", "check dependencies/SBOM", "threat-check these code paths". NOT for lint/type/test (delivery-gates), NOT for secret scanning (the pre-commit gitleaks hook owns that). Wraps the native security-review command over the diff.
---

# Security Review

## When to use
- "security review my changes", "run SAST on this diff", "check dependencies/SBOM"
- Before merging a branch that touches auth, input handling, deserialization, or dependencies
- You want threat-surface analysis of newly introduced code paths

## When NOT to use
- Lint, type-check, test, or coverage → use `delivery-gates`
- Secret/credential scanning → NOT a skill; the pre-commit gitleaks hook is the only place this runs
- Scaffolding security config into a fresh repo → use `repo-bootstrap`

## Inputs
- Operates on the git diff; no `org-profile.yaml` keys required
- Consumes the repo's existing dependency manifests/lockfiles for the SBOM pass

## Steps
1. Run the native `/security-review` command — it reviews the current working diff automatically (it takes no diff argument; do not try to pass one).
2. Fold its findings into the report.
3. Run/collect the dependency + SBOM pass against the lockfiles touched by the diff.
4. Perform a threat-check on the changed code paths (injection, authz gaps, unsafe deserialization, SSRF, path traversal).
5. Triage findings by severity; map each to a file:line and a concrete remediation.

## Output / validation
- Severity-ranked findings with file:line and remediation guidance, plus the SBOM delta
- Verify by re-running `/security-review` on the same diff; findings should be reproducible
- Does NOT report secrets — those are caught earlier by the pre-commit gitleaks hook

## Refuses when
- Asked to scan for secrets (out of scope; defer to the gitleaks pre-commit hook)
- (If `/security-review` is not present in the environment, say so plainly and fall back to a manual threat-check of the changed paths — do not claim a tool ran that didn't.)
