# VERIFY — azure-waf

Run after `azure-waf` has been applied to a live subscription (a Well-Architected pillar scoring). All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the report scores all 5 Well-Architected pillars — reliability, security, cost, operational excellence, performance — each with a score: `grep -qiE 'reliab' report.md && grep -qiE 'secur' report.md && grep -qiE 'cost' report.md && grep -qiE 'operation' report.md && grep -qiE 'perform' report.md && echo OK || echo MISSING`
- [ ] every pillar score is grounded in at least one live-resource finding (a REAL resource id from the az MCP), not generic WAF prose — and the remediation backlog items are severity-tagged + reference real resources: `grep -Eq '/subscriptions/[0-9a-fA-F-]+/' report.md && grep -qiE 'critical|high|medium|low|sev' report.md && echo OK || echo MISSING`
- [ ] scores reconcile with live `mcp__azure__advisor` / `mcp__azure__wellarchitectedframework` findings (each cited finding maps to its pillar by Advisor category) — no from-memory scores, no placeholder ids
- [ ] the cost pillar cross-refs `azure-cost` (dollar numbers) and the evidence base cross-refs `azure-audit` (inventory) — neither reimplemented here: `grep -q 'azure-cost' report.md && grep -q 'azure-audit' report.md && echo OK || echo MISSING`
- [ ] enforcement boundary stated: the report says it is advisory + read-only and names the real gate (Azure Policy `deny`/`audit` effects + CI required-checks + branch-protection), and that the score itself blocks/changes nothing: `grep -qiE 'advisory|read-only' report.md && grep -qiE 'azure policy|deny|required-check|branch.?protection' report.md && echo OK || echo MISSING`
- [ ] refuses (no fabricated score) when no live subscription is reachable via `mcp__azure__subscription_list`, when `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING`, or when asked to grade a pillar with no live-resource evidence

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` — note absent, don't fail (the skill drives the az MCP, not the local CLI, but its presence helps spot-check)
- [ ] az MCP reachable: a `mcp__azure__subscription_list` call returns at least one subscription — note if unreachable (then the skill should have refused)
- [ ] `command -v azqr` — the azqr extension, if an `azure-audit` snapshot is being consumed as the evidence base; note absent, don't fail

## Functional
Run the skill against a live (or sandbox) subscription. Take the pillar with the lowest score, resolve a cited resource id back through the inventory (`mcp__azure__group_resource_list` / the per-service tool) and confirm it is a real resource, then reconcile the score against the `mcp__azure__advisor` / `mcp__azure__wellarchitectedframework` recommendation it was sourced from so the grade is verifiable, not invented. Confirm the cost pillar's numbers defer to `azure-cost` and the evidence base defers to `azure-audit`. Confirm the run mutated nothing in the subscription (read-only) and that, with no subscription reachable, the skill refuses rather than scoring from memory.
