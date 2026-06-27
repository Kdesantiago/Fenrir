# VERIFY — delivery-gates

Run after `delivery-gates` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] compatibility precondition ran FIRST: `org-profile.yaml` exists and has a readable `template_version` → `grep -qE '^[[:space:]]*template_version:' org-profile.yaml && echo OK || echo MISSING`
- [ ] template_version is compatible with the installed plugin (major matches; for 0.x minor matches too) — re-run the skill's POSIX check and confirm it prints `DELIVERY-GATES: template_version OK`, NOT `INCOMPATIBLE`
- [ ] every reported stage maps to a real repo command: lint, type-check, test, coverage each ran against the diff (no invented tooling) and the report states it is ADVISORY, not an enforcement gate

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v ruff` · `command -v mypy` · `command -v pytest` (or the repo's actual configured tools) → note absent, don't fail
- [ ] `[ -f "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json" ]` — the version source the check reads → note absent

## Functional
- Re-run the same underlying lint/type/test commands manually on the diff; per-stage pass/fail must match the skill's report exactly (it only reports; it does not block).
