# VERIFY — azure-cost

Run after `azure-cost` has been applied (a live Azure FinOps pull). All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] every backlog line cites a REAL resource id + a dollar figure sourced from the az MCP (`mcp__azure__advisor` / `mcp__azure__pricing`), with an action — no placeholder ids, no from-memory numbers: `grep -Eq '/subscriptions/[0-9a-fA-F-]+/' backlog.md && grep -Eq '\$[0-9]' backlog.md && echo OK || echo MISSING` (or, if the backlog is in chat, manually confirm each line has `resource id · cost · action · savings · confidence · source`)
- [ ] a live subscription was actually confirmed via `mcp__azure__subscription_list` before any numbers were produced (the report names the subscription scanned, not a generic estimate)
- [ ] the report explicitly cross-refs `llm-cost-monitor` (LLM-API spend) and `us-cost-tracking` (per-US agent-token spend) as the OUT-OF-SCOPE owners of those other cost axes — no overlap claimed: `grep -q 'llm-cost-monitor' backlog.md && grep -q 'us-cost-tracking' backlog.md && echo OK || echo MISSING`
- [ ] the skill did NOT re-run a full live-subscription inventory that duplicates `azure-audit`: it either consumed an existing `azure-audit` snapshot as the resource spine, or built only the minimal billable-resource subset needed for costing (the report names which path it took): `grep -qi 'azure-audit' backlog.md && echo OK || echo CHECK-MANUALLY`
- [ ] the report states it is advisory + read-only and names the REAL cost gate — a CI budget check / Azure Budgets + a tagging/cost policy (Azure Policy), NOT this skill: `grep -Eqi 'advisor|read-only' backlog.md && grep -Eqi 'budget|azure budgets|polic' backlog.md && echo OK || echo MISSING`
- [ ] backlog is ordered low-risk-first then by dollar savings (delete-orphan / stop-billed before resize before buy-reservation), each line tagged with a confidence (high|medium|low)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` — note absent, don't fail (the skill drives the az MCP, not the local CLI, but its presence helps spot-check)
- [ ] az MCP reachable: a `mcp__azure__subscription_list` call returns at least one subscription — note if unreachable (then the skill should have refused)
- [ ] `command -v jq` — for spot-checking exported cost JSON; note absent, don't fail

## Functional
Run the skill against a live (or sandbox) subscription. Take the backlog's TOP item, resolve its cited resource id back through the inventory (`mcp__azure__group_resource_list` / the per-service tool) and confirm it is a real, currently-billed resource; then reconcile its estimated monthly savings against `mcp__azure__pricing` (or the Advisor figure it was sourced from) so the dollar delta is verifiable, not invented. Confirm the run mutated nothing in the subscription (read-only) and that, with no subscription reachable, the skill refuses rather than estimating from memory. Also confirm it did not re-enumerate the full live inventory that `azure-audit` owns — when an audit snapshot was available it was consumed as the spine; otherwise only the minimal billable-resource subset was pulled.
