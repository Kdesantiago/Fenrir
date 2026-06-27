# Contributing to Fenrir

Fenrir is a Claude Code plugin that installs a delivery standard (couche-0 gates +
profile-driven generators). It holds itself to the same bar it ships to others — so
contributions go through the same gate.

## Setup

```sh
uv sync --extra dev          # ruff, mypy, pytest
pre-commit install && pre-commit install --hook-type pre-push && pre-commit install --hook-type commit-msg
```

## The gate (run before you push)

```sh
uv run ruff check hooks      # lint first-party Python
uv run mypy hooks            # type-check
uv run pytest                # hook behavior tests
```

CI (`.github/workflows/ci.yml`) runs the same plus manifest/JSON/YAML validation as a
required check on PRs to `main`. A red gate blocks merge — fix it, don't bypass it
(`--no-verify` is denied by the in-session `delivery-guard` hook).

## Conventions

- **Branch + PR.** Work on a branch; open a PR to `main`. No direct pushes that skip CI.
- **Conventional commits.** `type(scope): subject` — `feat|fix|chore|docs|refactor|test|perf|build|ci`. Enforced at `commit-msg` and by the `release` skill's bump inference.
- **Changelog.** Add a `[Unreleased]` entry in `CHANGELOG.md` for any user-facing change (Keep a Changelog: Added/Changed/Fixed).
- **No secrets, ever.** `gitleaks` (pre-commit) is the authoritative block.

## Adding components

- **Skill** → `skills/<name>/SKILL.md` + `skills/<name>/VERIFY.md`. Match the existing
  shape: frontmatter (`name` + `description`), then `When to use` / `When NOT to use` /
  `Inputs` / `Steps` / `Output / validation` / `Refuses when`. The description must start
  with "Use when…", carry quoted trigger phrases, name the `org-profile.yaml` keys it
  reads, and point `NOT for` boundaries at the correct sibling skill.
- **Agent** → `agents/<name>.md` with YAML frontmatter (`name`, `description`, `tools`,
  `model`). Keep the body terse; preserve any machine-parsed output contract verbatim.
- **Hook** → `hooks/<name>.py` (stdlib only, runs as a script: stdin JSON → exit code +
  stdout decision). **Add tests in `hooks/tests/test_<name>.py`** covering its deny/ask/
  allow paths and malformed-input behavior. Wire it in `templates/.claude/settings.json`.

## Releasing

Cut releases with the `release` skill (infers the SemVer bump from conventional commits,
dates the changelog, tags `vX.Y.Z`, publishes). Don't hand-edit versions out of band.
