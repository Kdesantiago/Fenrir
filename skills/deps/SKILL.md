---
name: deps
description: Use when you want supply-chain hardening for THIS repo — a license-policy allowlist, deterministic pinning (lockfile + hashes), provenance/signing on built images, and a Renovate auto-merge policy. NOT for installing runtime dependencies, NOT for SAST (security-review). Extends the SBOM CI already emits; sets policy + names the CI check that fails on violation (it does not block itself). Reads org-profile.yaml `platform` to pick image-signing targets.
---

# Deps

## When to use
- "set a license allowlist", "pin dependencies with hashes", "sign our images / add provenance", "configure Renovate auto-merge"
- You want the supply chain hardened on top of the SBOM the CI pipeline already produces
- The org's uv/Python services need a reproducible, policy-checked dependency set

## When NOT to use
- Installing or upgrading a runtime dependency for a feature → just use the package manager (`uv add`, etc.)
- SAST / threat-check / SBOM generation itself → `security-review` (deps consumes the SBOM, it does not generate it)
- Wiring secret references / rotation → `secrets`

## Inputs
- `org-profile.yaml` → `platform` (selects image-signing/provenance targets; e.g. container platforms get `cosign`-signed images)
- The repo's lockfile and manifest (for the org's uv/Python stack: `pyproject.toml` + `uv.lock`)
- The existing CI workflow that emits the SBOM (deps adds policy checks alongside it)
- `renovate.json` (created/updated for the auto-merge policy)

## Steps
1. **License allowlist** — define the allowed-license set and add/point at the CI check that FAILS the build on a disallowed license (e.g. an SBOM/license-scan job in the pipeline). Name that check explicitly; the skill writes policy, the CI job is the enforcer.
2. **Pinning** — require a committed lockfile with hashes; for the uv/Python stack that is `uv.lock` (hash-pinned), installed with `--frozen`/`--locked` in CI so resolution is deterministic.
3. **Provenance + signing** — on built images, emit SLSA provenance and sign artifacts with `cosign` (keyless/OIDC where available); add a verify step so unsigned/unattested images fail the pipeline. Scope targets by `platform`.
4. **Renovate auto-merge** — `renovate.json` policy: patch/minor auto-merge ONLY after green required CI; major bumps require manual review (never auto-merged).
5. Record the policy (allowlist, pin strategy, signing keys/identities, auto-merge rules) so the enforcing CI jobs are discoverable.

## Output / validation
- A license allowlist tied to a named CI check, hash-pinned lockfile usage (`uv.lock` + `--frozen`), `cosign` signing/provenance + verify step, and a `renovate.json` auto-merge policy
- Verify: the license check fails on a planted disallowed license; `cosign verify` succeeds on a built image; a patch PR auto-merges after green CI while a major PR stays manual
- The skill sets policy and names the CI checks; those CI required-checks + branch-protection are the enforcement — the skill itself does not block a build

## Refuses when
- Asked to relax an existing license or pinning policy without an explicit, recorded exception — route that to `memory-keeper` (gate-exceptions: owner + mandatory expiry)
- Asked to auto-merge a major version bump, or to merge without green required CI
- Asked to ship unsigned/unattested images on a platform where signing applies
