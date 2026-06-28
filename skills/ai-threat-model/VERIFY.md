# VERIFY — ai-threat-model

Run after `ai-threat-model` has produced a threat model for a described LLM/agent system. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a findings doc exists at `docs/threat-models/<system>.md`: `ls "$CLAUDE_PROJECT_DIR"/docs/threat-models/*.md` returns at least one file
- [ ] the LLM-specific classes are actually enumerated for THIS system — at minimum prompt-injection (direct AND indirect), data-exfiltration, tool/function-abuse / excessive-agency, and jailbreak/guardrail-bypass each appear as a distinct threat row (not just listed as headings with no system-specific entry)
- [ ] every threat row ties to a real component with a `file:line` citation AND carries a likelihood×impact rating AND a concrete mitigation (a row with no component, no rating, or a generic "validate input" mitigation fails)
- [ ] no fabricated specifics: any OWASP-LLM reference is framing only — no invented rule IDs, no made-up CVE/limit/spec the repo can't support. Every cited `file:line` resolves to a real line in the repo (spot-check each); a hallucinated component or rule code fails the doc
- [ ] the doc does NOT claim to block/judge live prompts or to have run SAST/SBOM — it is a design-time analysis; any such claim means it overstepped into `security-guardrail` / `security-review` territory
- [ ] if `org-profile.yaml` `llm_provider` is `none`, the skill reported "no LLM surface" and wrote nothing — it did not fabricate threats

## Informational (does NOT block; note if absent)
- [ ] `org-profile.yaml` declares `llm_provider` (selects whether there is a surface at all) → note if missing
- [ ] the taxonomy is framed against the OWASP LLM Top-10 (framing only)

## Functional
- A reviewer can take any "fix first" item and locate the exact component (`file:line`) + the proposed mitigation from the row alone.

## Design intent (not machine-checked)
- Re-running on the same described system should reproduce the same threat set (same classes, same components) — the enumeration is meant to be grounded in the repo, not a random draw; this is intent, not a post-hoc gate.
