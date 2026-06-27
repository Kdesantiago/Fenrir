# VERIFY — doc-generator

Run after `doc-generator` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the aggregated docs exist and were refreshed: `[ -f README.md ] && echo OK || echo MISSING` (plus the API-reference and changelog targets the repo uses)
- [ ] the changelog section was built from conventional commits since the last tag: every `[X.Y.Z]`/`[Unreleased]` entry maps to a real commit subject — spot-check `git log $(git describe --tags --abbrev=0 2>/dev/null)..HEAD --oneline` against the entries
- [ ] API reference matches CURRENT code: each documented symbol traces to a real signature/docstring (no invented behavior), and ADR/design-rationale sections were left untouched / flagged out of scope

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v git` (commit history source) · the repo's docstring/API extractor if any → note absent, don't fail

## Functional
- Diff a regenerated symbol's documented signature against the source signature; they must agree. Every changelog line resolves to an actual commit (no fabricated entries).
