---
name: release
description: Use when you want to cut a versioned release of THIS repo/plugin — pick the SemVer bump by the Fenrir delivery cadence (feature PR → patch +1, finished epic → minor, breaking → major), bump version, date the changelog, tag, and publish. NOT for deploying to an environment (that is iac-gen / a deploy pipeline). Reads CHANGELOG.md `[Unreleased]`, bumps `version` in .claude-plugin/plugin.json (+ pyproject.toml if present), tags `vX.Y.Z`, and publishes via `gh release` / `az repos`. Reads org-profile.yaml `platform` only to pick the publish target.
---

# Release

## When to use
- "cut a release", "tag and publish", "bump the version and ship release notes"
- The `[Unreleased]` section of CHANGELOG.md has entries and the working tree is clean
- You want the git tag, the version field, and the changelog heading to all agree on one SemVer

## When NOT to use
- Deploying built artifacts to dev/prod or rolling out infra → use `iac-gen` + the deploy pipeline
- Filling `[Unreleased]` / generating the changelog from commits → `doc-generator` owns that; run it first
- Recording a release decision or a gate-exception → `memory-keeper`

## Versioning cadence (the Fenrir rule — this is how the bump is chosen)

The bump follows **delivery**, not a raw commit-type tally:

- **Feature PR merged → patch +1** (`vX.Y.Z` → `vX.Y.(Z+1)`). Each Feature shipped within the current minor line just advances the patch. (One Feature = one branch = one PR — see `/fenrir:plan`.)
- **Epic finished → minor +1, patch → 0** (`vX.Y.Z` → `vX.(Y+1).0`). When the **last US of an Epic reaches `done`** (the board rolls the epic to `done` and writes its retro), the next release graduates the minor. The epic's retro (`docs/delivery-memory/retros/`) is the human-readable "what this minor delivered".
- **Breaking change → major +1, minor/patch → 0** (`!`/`BREAKING CHANGE:` in commits since the last tag). Always wins over the above.

So a minor line accumulates patch releases (one per feature PR) and **closes** when its epic completes → the minor bump.

## Inputs
- `CHANGELOG.md` → the `[Unreleased]` section (the source of the release notes; must be non-empty)
- **The board** (`cd dashboard && python -m backend.cli list`) → each epic's `status` + `transitions`. An epic with a `→ done` transition timestamped **after the last release tag's date** = an epic finished this cycle → **minor**.
- Conventional-commit subjects since the last `v*` tag → detect **breaking** (`!`/`BREAKING CHANGE:` → major) and confirm at least one `feat:`/`fix:` exists (else nothing to release).
- `.claude-plugin/plugin.json` → `version` (bumped); `pyproject.toml` → `[project].version` (bumped if the file exists)
- `org-profile.yaml` → `platform` (ONLY to select publish target: Azure-flavored profiles → `az repos`/pipeline; otherwise GitHub `gh`)

## Steps
1. Verify the working tree is clean (`git status --porcelain` empty) and you are on the release branch. If dirty, REFUSE.
2. Find the last release tag (`git describe --tags --abbrev=0 --match 'v*'`) and its date (`git log -1 --format=%cI <tag>`); collect commit subjects since it.
3. **Choose the bump by the cadence rule** (in order): (a) any `BREAKING CHANGE:`/`type!:` since the tag → **major**; (b) else an epic reached `done` after the last tag's date (board transitions) → **minor** (reset patch to 0); (c) else (feature PR(s) merged — `feat:` present) → **patch +1**. Compute `X.Y.Z`. State which rule fired and why.
4. Read `CHANGELOG.md`. If `[Unreleased]` is empty, REFUSE (nothing to release; run `doc-generator` first).
5. Confirm `vX.Y.Z` does not already exist (`git tag -l vX.Y.Z` empty, and not on the remote). If it exists, REFUSE.
6. Bump `version` in `.claude-plugin/plugin.json`; if `pyproject.toml` exists, bump `[project].version` to the SAME `X.Y.Z`.
7. Rename `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD` and open a fresh empty `[Unreleased]` above it.
8. Commit the version + changelog change, then create the annotated tag `vX.Y.Z` (the tag MUST equal the bumped version).
9. Generate release notes from the just-dated `[X.Y.Z]` section.
10. Publish: GitHub → `gh release create vX.Y.Z --notes-file <notes>`; Azure → `az repos`/pipeline release with the same notes.

## Output / validation
- One commit bumping `version` (plugin.json + pyproject.toml in lockstep), a dated `[X.Y.Z]` changelog section, an annotated `vX.Y.Z` tag, and a published release
- Verify: `git describe --tags` returns `vX.Y.Z`; the tag, `plugin.json` `version`, and the changelog heading are byte-for-byte the same `X.Y.Z`
- This skill versions and publishes a release; it does NOT deploy. Promotion to an environment is the deploy pipeline's job, gated by CI required-checks + branch-protection (not by this skill).

## Refuses when
- The working tree is dirty (uncommitted changes) or not on the release branch
- `[Unreleased]` in `CHANGELOG.md` is empty / missing — nothing to release
- The computed tag `vX.Y.Z` already exists locally or on the remote
- The inferred version and the proposed tag would disagree (tag must match the bumped `version`)
