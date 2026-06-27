# VERIFY — quality-master

Run after `quality-master` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] mypy is strict: `grep -qE '^\s*strict\s*=\s*true' pyproject.toml mypy.ini 2>/dev/null && echo OK || echo MISSING` — and its components are on (`disallow_untyped_defs`, `warn_return_any`, `no_implicit_optional`, `warn_unused_ignores`)
- [ ] ruff `select` is broadened (e.g. `E,F,W,I,N,UP,B,C4,SIM,ARG,PTH,RUF`) and EVERY relaxation lives in `per-file-ignores` with a justification — no blanket `ignore` without a reason
- [ ] pytest expert strategy wired: a `--cov` fail-under threshold, `--strict-markers` with `unit|integration|e2e` registered, parametrize/Hypothesis in use, and a test-plan doc mapping the public surface → required tests
- [ ] RATCHET-UP only — no previously-stricter setting was loosened (compare against the pre-existing config; a lowered setting is a failure). Output matches `org-profile.yaml` `framework` test idioms

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v mypy` · `command -v ruff` · `command -v pytest` · `python3 -c 'import hypothesis'` → note absent, don't fail

## Functional
- `ruff check` passes with only justified ignores, `mypy` runs clean under strict (or lists honest debt), and `pytest -m unit --strict-markers` selects correctly with the coverage fail-under enforced.
