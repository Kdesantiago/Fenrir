---
name: cli
description: >-
  Use-when build or extend a command-line interface — "add a CLI / subcommand",
  "parse these args", "set the exit code", "make it read stdin / pipe-friendly",
  "improve the --help". Path — `src/<module>/cli.py` or a `console_scripts`
  entry-point. NOT-for an HTTP endpoint/contract → use api-first; a scheduled or
  background job's trigger → use cronjob; the business logic the command calls →
  use domain-services. Refuses-when the org-profile stack mismatches/is unset |
  asked to design the architecture (→ architect) | asked to gate/merge (→ reviewer)
  | touches a gate file (.claude/, CI).
tools: Read, Grep, Glob, Edit, Write, Bash
model: inherit
---

# cli — the command-line contract a script forgets

This skill implements the CLI surface: argument parsing, subcommands, exit codes, and the stdin/stdout contract — a thin adapter that parses, delegates to `domain-services`, and translates the result into an exit status. It is ZERO-cloud — it works with no `az`/`terraform`/`kubectl`/`gh`. The core rule: **a command parses its args, does its work, and signals success or failure through the exit code — never a side effect at import, never a bare `print` for an error, never a hung pipe.**

## When to use
- "add a CLI / a subcommand", "parse these flags / positional args"
- "set the right exit code", "make this script pipe-friendly / read stdin"
- "improve the `--help` / usage", "validate the args before running"
- A script that grew flags ad-hoc and needs a real parser + exit-code contract

## When NOT to use
- An HTTP endpoint / request-response contract → `api-first` (the CLI calls the same service, it is not a transport)
- The trigger/schedule for a recurring or background job → `cronjob` (CLI is the manual entry-point, not the scheduler)
- The business logic the command invokes → `domain-services` (the command stays a thin adapter; logic lives below it)

## Inputs
- The command(s) to add: name, positional args, options/flags, defaults, and which are required.
- The parsing library in use (stdlib `argparse`, or `click`/`typer` if the repo already depends on one) — REUSE the existing one, do not add a parser dependency unprompted.
- The success/failure semantics: what each non-zero exit code means, and whether the command reads stdin or writes machine-readable stdout.

## Steps
1. **One parser, declarative.** Define args/subcommands declaratively (`argparse`/`click`/`typer`); group subcommands under one dispatcher. Every option has a help string; required vs optional is explicit.
2. **No side effects on import.** Parsing and execution live behind a `main(argv=None)` function called from `if __name__ == "__main__":` / a `console_scripts` entry-point — importing the module must run nothing (no I/O, no parse, no exit).
3. **Exit codes are the contract.** Return `0` on success, non-zero on failure (`2` for usage/arg errors, distinct codes for distinct failure classes). The shell sees the code; never `sys.exit(0)` on an error.
4. **stdout for data, stderr for diagnostics.** Machine-readable result → stdout; logs, prompts, and errors → stderr. Honor a `--quiet`/`--json` where it makes the output pipeable; never interleave diagnostics into piped data.
5. **stdin when piped.** If the command can take input from a pipe, read stdin (`-` convention or no-arg fallback) and don't block on a TTY prompt in a non-interactive run.
6. **Validate args, fail with usage.** Bad/missing args exit `2` with a clear message + usage on stderr — not a stack trace. Catch the domain error from the service layer and map it to a code + a one-line stderr message.
7. **Delegate, don't compute.** The command parses then calls a `domain-services` use-case; it holds no business logic itself. Help/usage text is the UX surface — keep it accurate and example-bearing.

## Output / validation
- A CLI module: one declarative parser, subcommands under a dispatcher, a `main(argv)` with zero import-time side effects, an exit-code map (0 / 2 / domain-failure), stdout-for-data + stderr-for-diagnostics, stdin when piped, and arg validation that exits `2` with usage — delegating real work to `domain-services`.
- Validation: `import`ing the module runs nothing; `main(["--help"])` prints usage and exits `0`; a bad arg exits `2` with a stderr message; a happy path exits `0`; a known failure exits its mapped non-zero code; piped stdin is consumed and stdout stays clean of diagnostics.
- Boundary: this skill owns the CLI adapter, not the logic it calls or the deployment. The teeth are the VERIFY exit-code + no-import-side-effect checks + the qa-tester/red-team gate. VERIFY greps are scoped to the CLI module — a backstop, not a proof; the functional exit-code check is.

## Optional Azure layer (one-line pointer, opt-in)
When `org-profile.yaml` sets `cloud_layer: azure`, a command MAY shell to an Azure operation, but only opt-in and through the `stack-adapter`/an injected port — never an inlined `az`; the core CLI ships with no `az`/`terraform`/`kubectl`/`gh` and never loads or blocks the cloud layer for a local user.

## Refuses when
- `org-profile.yaml` missing, or the stack is not the supported (Python) shape for the repo's parser.
- Asked to run work or parse args at import time (defeats testability and pollutes any importer) — put it behind `main()`.
- Asked to swallow failures and exit `0`, or to write errors/diagnostics to stdout where they corrupt piped data.
- Asked to put business logic in the command (→ `domain-services`), to design the architecture (→ architect), to gate/merge (→ reviewer), or to touch a gate file (`.claude/`, CI).
