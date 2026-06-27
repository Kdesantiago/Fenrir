---
name: image-scan
description: Use when you want container base-image / OS-layer CVE scanning of a BUILT image as a named CI required-check — "scan my image for CVEs", "fail the build on HIGH/CRITICAL vulns", "Trivy/Grype scan", "Defender for Containers scan". Scans after build+push to ACR, before deploy. NOT for SAST on the source diff (security-review), NOT for license policy / SLSA provenance / cosign signing (deps). Reads org-profile.yaml `platform`; refuses when the platform builds no container images, or asked to do SAST/signing.
---

# Image Scan

The build is the easy part. This skill's job: catch the vulnerable OS packages and base-image CVEs that ship *inside* the image you already built, and make the pipeline refuse to deploy them.

## When to use
- "scan the container image for CVEs", "fail CI on HIGH/CRITICAL vulnerabilities in the built image"
- "add Trivy/Grype to the pipeline", "turn on Defender for Containers / ACR built-in scanning"
- You want a named required-check that runs **after build+push to ACR, before deploy**

## When NOT to use
- SAST / threat-check on the source diff → `security-review`
- License-policy allowlist, SLSA provenance, `cosign` signing/verify of artifacts → `deps` (do not duplicate)
- The declared `platform` builds no container images → this skill refuses

## Inputs
- `org-profile.yaml` → `platform` — REQUIRED; only container-building platforms apply: `aks` / `k8s` / `webapp-container` / `ecs`
- The built image reference (registry/repo:tag, e.g. the ACR-pushed image)
- The existing CI workflow (the scan job is inserted between push and deploy)
- Severity threshold + optional ignore policy (`.trivyignore` / VEX) for accepted CVEs

## Steps
1. Read `org-profile.yaml`; resolve `platform`. If it builds no container images (not `aks`/`k8s`/`webapp-container`/`ecs`), REFUSE.
2. **Pick the scanner**: **Trivy** (default), or **Grype**, or **Azure Defender for Containers / ACR built-in (Microsoft Defender)** scanning when the org prefers registry-side scanning.
3. **Write the scan policy**: fail on `HIGH,CRITICAL`; scan OS packages + base-image layers of the *built* image (not the source). Record accepted-CVE exceptions in `.trivyignore`/VEX with owner + expiry (route waivers to `memory-keeper`).
4. **Place the job after build+push to ACR, before deploy**: scan the pushed image by digest. Name the CI check explicitly (e.g. `image-scan`) so it is selectable as a required-check.
5. The scan job exits non-zero on a threshold breach; the named required-check + branch-protection are the enforcement — the skill writes policy and names the check, it does not block by itself.

## Output / validation
- A scan job (Trivy/Grype/Defender) wired after push, before deploy, with a named CI check failing on HIGH/CRITICAL
- Verify: a planted vulnerable base image fails the named check; a clean image passes; an accepted CVE in `.trivyignore`/VEX is suppressed
- The required-check + branch-protection enforce the gate; the skill itself does not block

## Refuses when
- `platform` is unset or builds no container images (route platform fixes to `repo-bootstrap`/`iac-gen`)
- Asked to do SAST on the source diff → `security-review`
- Asked to sign/attest images, add SLSA provenance, or enforce license policy → `deps`
- Asked to waive a CVE without a recorded exception (owner + mandatory expiry) → `memory-keeper`

## Sources
- Trivy CI scanning + exit codes: https://aquasecurity.github.io/trivy
- Grype: https://github.com/anchore/grype
- Microsoft Defender for Containers: https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction
