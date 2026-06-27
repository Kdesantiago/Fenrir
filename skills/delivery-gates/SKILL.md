---
name: delivery-gates
description: Use when you want fast local lint+type+test+coverage feedback on a git diff before pushing. NOT for initializing a repo (repo-bootstrap), NOT for SAST/SBOM/threat-check (security-review). Runs the repo's existing quality tooling on the working diff for fast feedback only — it does not block.
---

# Delivery Gates

## When to use
- "run the gates on my changes", "check lint/types/tests before I push"
- You have a dirty working tree or a feature branch and want quick pass/fail on the diff
- Pre-push sanity check that mirrors what CI will run

## When NOT to use
- Repo has no tooling/config yet, or you need hooks/CI/branch-protection installed → use `repo-bootstrap`
- You need SAST, dependency/SBOM, or threat analysis → use `security-review`
- Secret scanning → this is NOT a skill; it lives only in the pre-commit gitleaks hook
- An SLO/error-budget release freeze → use `error-budget` (a different gate, tied to observability)

## Inputs
- `org-profile.yaml` → `template_version` (the plugin major.minor this repo targets)
- The installed plugin's `version`, read from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`
- Reads the repo's existing tool configs (lint/type/test/coverage); does not invent them

## Compatibility check (template_version)

This runs FIRST, before any gate. It is a hard precondition.

**Where the versions come from**
- Installed plugin version: the `version` field of `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`. `CLAUDE_PLUGIN_ROOT` is set by Claude Code to the installed plugin's root; if unset, fall back to the plugin root relative to this skill (`../../.claude-plugin/plugin.json`).
- Target version: the `template_version` field of the repo's root `org-profile.yaml`.

**How they are compared (semver, major-match with a 0.x rule)**
- Parse both as `MAJOR.MINOR.PATCH`.
- **Compatible iff `MAJOR` is equal.** A major bump is the breaking-change signal; patch and minor differences within the same stable major are forward/backward compatible and are allowed.
- **Pre-stable exception:** when `MAJOR == 0`, `MINOR` must ALSO be equal. Under semver, 0.x carries no stability guarantee, so each 0.x minor is treated as its own compatibility line. (`0.1.x` ~ `0.1.x` is OK; `0.1.x` vs `0.2.x` is INCOMPATIBLE.)
- `PATCH` is never compared.

**What "incompatible" does**
- FAIL LOUD to stderr with `DELIVERY-GATES: INCOMPATIBLE — <reason>`, naming both versions and the fix, and STOP with a non-zero exit. No gates run. Never silently run stale gates against a mismatched plugin.
- Missing `org-profile.yaml`, an unreadable `template_version`, a missing `plugin.json`, or an unreadable plugin `version` are all treated as incompatible (fail loud, stop).

**Runnable check** (POSIX `sh`; no `jq`/`bash`-isms — portable across macOS and Linux CI):

```sh
#!/bin/sh
# delivery-gates: template_version compatibility check.
# Compatible iff MAJOR matches (and, for 0.x, MINOR also matches).
# Exits non-zero with a loud message on mismatch or missing input.
set -eu

PROFILE="${1:-org-profile.yaml}"
PLUGIN_JSON="${2:-${CLAUDE_PLUGIN_ROOT:-.}/.claude-plugin/plugin.json}"

fail() { printf 'DELIVERY-GATES: INCOMPATIBLE — %s\n' "$1" >&2; exit 1; }

[ -f "$PROFILE" ]     || fail "org-profile.yaml not found at '$PROFILE' (required)."
[ -f "$PLUGIN_JSON" ] || fail "plugin.json not found at '$PLUGIN_JSON' (plugin not installed?)."

# template_version: "X.Y.Z" from YAML (tolerates quotes/whitespace).
PROFILE_VER=$(sed -n 's/^[[:space:]]*template_version:[[:space:]]*["'\'']*\([0-9][0-9.]*\)["'\'']*.*$/\1/p' "$PROFILE" | head -n1)
# "version": "X.Y.Z" from plugin.json (no jq dependency).
PLUGIN_VER=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([0-9][0-9.]*\)".*/\1/p' "$PLUGIN_JSON" | head -n1)

[ -n "$PROFILE_VER" ] || fail "org-profile.yaml has no readable template_version."
[ -n "$PLUGIN_VER" ]  || fail "plugin.json has no readable version."

P_MAJ=${PROFILE_VER%%.*}; P_REST=${PROFILE_VER#*.}; P_MIN=${P_REST%%.*}
I_MAJ=${PLUGIN_VER%%.*};  I_REST=${PLUGIN_VER#*.};  I_MIN=${I_REST%%.*}

if [ "$P_MAJ" != "$I_MAJ" ]; then
  fail "org-profile template_version $PROFILE_VER targets major v$P_MAJ but installed plugin is $PLUGIN_VER (major v$I_MAJ). Bump org-profile.yaml or install a matching plugin."
fi
if [ "$P_MAJ" = "0" ] && [ "$P_MIN" != "$I_MIN" ]; then
  fail "org-profile template_version $PROFILE_VER and installed plugin $PLUGIN_VER differ in minor (0.x is pre-stable — minor bumps may break). Align them."
fi

printf 'DELIVERY-GATES: template_version OK (profile %s ~ plugin %s).\n' "$PROFILE_VER" "$PLUGIN_VER"
```

## Steps
1. Run the compatibility check above. If it exits non-zero, FAIL LOUD and STOP — do not run any gates.
2. Compute the diff scope: changed files vs. the base branch (or staged/unstaged if no base).
3. Run the repo's existing commands in order, scoped to the diff where the tool supports it:
   - lint
   - type-check
   - test
   - coverage (compare against the repo's configured threshold)
4. Collect results; report per-stage pass/fail with the failing file:line.
5. State explicitly in the output that this is ADVISORY fast feedback, not an enforcement gate.

## Output / validation
- Per-stage pass/fail summary plus the exact failing locations
- Verify by re-running the same underlying commands manually; results must match
- The authoritative enforcement is CI required-checks + branch-protection installed by `repo-bootstrap`, NOT this skill

## Refuses when
- `org-profile.yaml` is missing, or its `template_version` is unreadable
- The installed `plugin.json` is missing/unreadable, or its `version` is incompatible (major differs; or, for 0.x, minor differs) — see the compatibility check above
- The repo has no resolvable lint/type/test tooling (route to `repo-bootstrap` instead)
