# VERIFY — image-scan

Run after `image-scan` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a container-image scan job exists using Trivy (default), Grype, or Azure Defender for Containers / ACR built-in scanning — and it scans the BUILT image (by digest/tag), not the source tree
- [ ] the scan policy FAILS on `HIGH,CRITICAL` CVEs (e.g. Trivy `--severity HIGH,CRITICAL --exit-code 1`) — `grep -rEi '(severity).*(HIGH|CRITICAL)' <ci-dir>` and a non-zero exit on breach
- [ ] the job is placed AFTER build+push to ACR and BEFORE deploy (scan the pushed image, then deploy only on pass)
- [ ] the check is NAMED so branch-protection can require it (a stable job/check name, e.g. `image-scan`, selectable as a required-check)
- [ ] accepted-CVE exceptions are recorded with owner + expiry (`.trivyignore`/VEX), not silently dropped — `[ -f .trivyignore ] && echo OK || echo "none (ok if no exceptions)"`
- [ ] matches `org-profile.yaml`: `platform` is a container-building platform (`aks`/`k8s`/`webapp-container`/`ecs`); otherwise the skill must have REFUSED
- [ ] no scope bleed: this job does NOT do SAST (→ `security-review`) and does NOT sign/attest or enforce license policy (→ `deps`)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v trivy` · `command -v grype` (or Defender for Containers enabled on the subscription/ACR) → note absent, don't fail

## Functional
- Scan a known-vulnerable base image (e.g. an old `debian`/`node` tag) → the named check FAILS. Scan a patched/clean image → it PASSES. Add an accepted CVE to `.trivyignore`/VEX → that CVE is suppressed while others still fail. The required-check + branch-protection are what block the merge/deploy; the skill itself does not.
