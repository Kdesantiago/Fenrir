---
name: doc-generator
description: Use when you want to aggregate and format EXISTING docs — README, API reference from code, changelog from conventional commits. NOT for writing ADRs or design decisions (the architect subagent owns those). Assembles and formats documentation that already exists in the code and git history.
---

# Doc Generator

## When to use
- "regenerate the README/API docs/changelog", "format the docs from the code"
- API reference needs to be derived from current code signatures/docstrings
- Changelog needs to be built from conventional-commit history

## When NOT to use
- Writing or deciding an ADR (architecture decision record) → the architect subagent decides and writes ADRs
- Designing a system, weighing trade-offs, or producing net-new design narrative → not this skill
- Generating code/config → use the relevant `*-gen` skill

## Inputs
- No required `org-profile.yaml` keys
- Reads existing sources: README, code (signatures/docstrings), conventional-commit history

## Steps
1. Inventory existing doc sources: README, in-code docstrings/annotations, commit history.
2. Generate the API reference strictly from current code signatures/docstrings (do not invent behavior).
3. Build the changelog from conventional commits, grouped by type (feat/fix/etc.) since the last tag.
4. Aggregate into the repo's documentation layout and apply consistent formatting.
5. Leave decision-narrative sections (ADRs, design rationale) untouched — flag them as out of scope.

## Output / validation
- Updated README/API docs/changelog reflecting current code and commit history
- Verify API docs match actual signatures; verify changelog entries map to real commits
- No fabricated content: every line traces back to code or a commit

## Refuses when
- Asked to author or decide an ADR or design rationale (defer to the architect subagent)
- The repo lacks conventional commits AND has no derivable code docs to aggregate
