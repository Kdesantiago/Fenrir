# VERIFY — deps

Run after `deps` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a license allowlist is defined AND tied to a NAMED CI check that fails on a disallowed license (the policy points at a real job in the pipeline, not a promise)
- [ ] deterministic hash-pinned lockfile committed and installed frozen: `[ -f uv.lock ] && echo OK || echo MISSING`, and CI uses `uv sync --frozen`/`--locked` (`grep -rE 'uv (sync|pip).*(--frozen|--locked)' <ci-dir>`)
- [ ] image provenance + signing wired for the declared `platform`: `cosign` sign/attest step on built images PLUS a `cosign verify` step that fails the pipeline on unsigned/unattested images
- [ ] `renovate.json` auto-merge policy present and correct: patch/minor auto-merge ONLY after green required CI, major bumps stay MANUAL — `[ -f renovate.json ] && python3 -c "import json;c=json.load(open('renovate.json'));print('OK')"`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v uv` · `command -v cosign` · `command -v syft`/`command -v grype` (license/SBOM scan) → note absent, don't fail

## Functional
- Plant a disallowed-license dep → the named license check fails. `cosign verify` succeeds on a built signed image. A patch PR auto-merges after green CI while a major PR remains manual.
