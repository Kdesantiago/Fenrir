# VERIFY — release

Run after `release` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] tag, version field, and changelog heading all agree on ONE `X.Y.Z`: `git describe --tags` returns `vX.Y.Z`; `grep '"version"' .claude-plugin/plugin.json` equals that `X.Y.Z`; and `grep -E '^\#* \[X\.Y\.Z\] - [0-9]{4}-[0-9]{2}-[0-9]{2}' CHANGELOG.md` matches (byte-for-byte same version)
- [ ] the annotated tag exists exactly once: `git tag -l vX.Y.Z` non-empty and `git cat-file -t vX.Y.Z` = `tag` (annotated, not lightweight)
- [ ] changelog rotated correctly: the released section is dated `[X.Y.Z] - YYYY-MM-DD` and a fresh empty `[Unreleased]` sits above it
- [ ] if `pyproject.toml` exists, `[project].version` was bumped to the SAME `X.Y.Z` in lockstep; the bump level matches the **Fenrir cadence**: an epic reached `done` after the last tag → **minor** (patch reset to 0); else feature PR(s) merged → **patch +1**; `!`/`BREAKING CHANGE:` → **major**

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v gh` (GitHub publish) or `command -v az` (Azure publish) → note absent, don't fail
- [ ] `command -v git` (tagging) → note absent

## Functional
- A release was published (`gh release view vX.Y.Z` / `az repos` release exists) carrying notes generated from the just-dated `[X.Y.Z]` section; the working tree was clean before tagging (`git status --porcelain` empty). This skill versions/publishes only — it does not deploy.
