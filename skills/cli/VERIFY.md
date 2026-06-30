# VERIFY — cli

Run after `cli` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **CLI module(s)** — the file(s) that define the parser / `main(argv)` / `console_scripts` entry-point — not the whole repo. A repo-wide search is not falsifiable (a stray `argparse` import or a `sys.exit` in unrelated code would pass with zero CLI contract). Resolve the CLI file(s) first, then run the co-located checks against them:

```
CLI_FILES=$(grep -rlE 'argparse|ArgumentParser|\bclick\b|\btyper\b|add_subparsers|console_scripts' --include='*.py' . )
echo "${CLI_FILES:-<none — no CLI module found, FAIL>}"
```
If `CLI_FILES` is empty, the skill produced no wired CLI surface → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **a declarative parser is defined** — args/subcommands via a parser, not hand-rolled `sys.argv` slicing: `for f in $CLI_FILES; do grep -qE 'ArgumentParser|add_argument|add_subparsers|@(app\.)?command|click\.(command|option|argument)|typer\.' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-PARSER`
- [ ] **no side effects on import** — work lives behind a `main()` guarded by `__main__`, nothing runs at import: `for f in $CLI_FILES; do grep -qE 'def main\(|if __name__ == .__main__.|console_scripts|\[project.scripts\]' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NO-MAIN-GUARD`
- [ ] **exit code is the contract** — success/failure signaled through the exit status, not just a print: `for f in $CLI_FILES; do grep -qE 'sys\.exit|raise SystemExit|return [0-9]|exit_code|typer\.Exit|click\.exceptions\.Exit' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NO-EXIT-CODE`
- [ ] **errors/diagnostics to stderr, not stdout** — a usage/error path writes to stderr (so stdout stays pipeable): `for f in $CLI_FILES; do grep -qE 'sys\.stderr|file=sys\.stderr|parser\.error|click\.echo\(.*err=True|typer\.echo\(.*err=True|\.error\(' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NO-STDERR-DIAGNOSTICS`
- [ ] **no business logic inline** — the command delegates to a service, it doesn't compute (skip-OK only if the file is pure parsing): `for f in $CLI_FILES; do grep -qE 'services\.|import .*service|use_case|\.run\(|domain' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo NOTE-confirm-command-is-a-thin-adapter`
- [ ] **cloud-agnostic core** — the CLI carries no hard cloud dependency (runs with no `az`/`terraform`/`kubectl`/`gh`): `! grep -rEq 'subprocess.*\b(az|kubectl|terraform|gh)\b|DefaultAzureCredential|\bos\.system\(.*\b(az|kubectl)\b' $CLI_FILES && echo OK || echo CLOUD-DEP-IN-CLI`
- [ ] (profile-driven) the org-profile stack is the supported (Python) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] **`--help` is example-bearing** — help strings present on options/subcommands (UX surface): `for f in $CLI_FILES; do grep -qE "help=|\"\"\"|'''|click\.option\(.*help" "$f" && echo "help text present"; done || echo "NOTE: no help= strings — confirm usage UX is intentional"`
- [ ] **stdin handling** noted where the command is meant to be pipeable: `grep -rqE 'sys\.stdin|click\.get_text_stream|\bstdin\b|argparse\.FileType' $CLI_FILES && echo "stdin wired" || echo "NOTE: no stdin read — expected for a non-pipe command"`
- [ ] **entry-point registered** in `pyproject.toml` (`[project.scripts]`/`console_scripts`) noted — advisory, not a gate

## Functional
Exercise the CLI module directly, no cloud CLI on PATH: (1) `import` the module and confirm nothing runs (no I/O, no parse, no exit at import); (2) call `main(["--help"])` and confirm usage prints and the exit code is `0`; (3) pass a bad/missing arg and confirm it exits `2` with a message on **stderr** (not a stack trace, not stdout); (4) run a happy path and confirm exit `0` with the machine-readable result on stdout; (5) trigger a known failure and confirm the mapped non-zero exit code; (6) where the command reads stdin, pipe input in non-interactively and confirm it is consumed without blocking on a TTY and stdout stays free of diagnostics.
