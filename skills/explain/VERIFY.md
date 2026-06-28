# VERIFY — explain

Run after `explain` has been applied to a target (a file/function/module explanation). All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the explanation is grounded in the ACTUAL code — every behavioral claim cites `file:line` and resolves to a real line in the target (no invented behavior): pick a cited claim and run `f=<file>; n=<line>; sed -n "${n}p" "$f" >/dev/null 2>&1 && echo OK || echo MISSING`
- [ ] pedagogy order holds: the mental model + the WHY precede any line-level detail (not a raw line dump) — the opening frames the problem/shape/data-flow before annotating lines
- [ ] the depth knob (`overview` | `walkthrough` | `line-by-line`) and audience knob (`junior` | `senior` | `non-engineer`) are honored AND stated up front: `echo "$EXPLAIN_OUTPUT" | grep -Eiq 'depth.*(overview|walkthrough|line-by-line)' && echo OK || echo MISSING`
- [ ] read-only contract: nothing was edited or written to disk by this skill (no source/test/doc/ADR mutation) — `git diff --quiet && echo OK || echo "MUTATED — explain must not edit"`
- [ ] unclear / externally-dependent behavior is FLAGGED as such, not guessed; out-of-scope asks are routed (durable doc → `doc-generator`, decision → `architect`, correctness/security → `/code-review`/`security-review`, restructuring → `fenrir:refactor`)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v git` (to assert the read-only/no-mutation check) → note absent, don't fail
- [ ] `command -v rg` or `command -v grep` (to resolve symbol definitions/usages before explaining) → note absent, don't fail

## Functional
Point the skill at a real non-trivial function in this repo and request, say, `depth: walkthrough, audience: junior`. Confirm the explanation opens with the stated depth/audience, gives the mental model and the WHY before any per-line detail, and that each behavioral claim's `file:line` resolves to the actual line in the file. Then run `git status --porcelain` and confirm it is empty — the explanation changed nothing on disk.
