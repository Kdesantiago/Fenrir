# {{PROJECT_NAME}}

A uv-workspace monorepo. One lockfile (`uv.lock`) at the root; each service is a workspace member under `src/`.

## Layout
```
pyproject.toml            # workspace root (virtual): members, shared dev tooling, ruff/mypy/pytest config
uv.lock                   # single resolved lockfile for the whole workspace
src/<service>/            # one workspace member = one shippable service
  pyproject.toml          #   its runtime deps + build config
  <package>/              #   the importable package
  tests/                  #   its tests
docs/  scripts/
```

## Develop
```bash
uv sync --all-packages --dev  # one venv, ALL workspace members (editable) + dev tools
uv run pytest                 # run the whole suite
uv run ruff check . && uv run mypy src
```

> Use `--all-packages` (not just `--dev`): the virtual root doesn't depend on the members, so without it `uv sync` won't install them and imports fail.

## Add a service
Copy `src/example_service` → `src/<new>`, rename the package + `pyproject.toml` `name`, then `uv lock`.

> Bootstrapped by `/fenrir:init`; the delivery gate (pre-commit + CI + branch-protection) is installed by `repo-bootstrap`.
