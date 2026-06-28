# VERIFY — azure-audit

Run after `azure-audit` has been applied to a live subscription. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the snapshot has all three sections grounded in real az MCP data — inventory, azqr findings (the single compliance verdict, annotated with policy-effect metadata), resource health — each finding carrying a real resource id: `grep -qiE 'inventor|azqr|resource health' snapshot.md && echo OK || echo MISSING` (and every id resolves to a real resource, not a placeholder)
- [ ] exactly ONE compliance view: compliance lives inside the azqr findings (azqr is the source of record); there is NO separate standalone "policy compliance" section re-deriving a second per-resource verdict that could contradict azqr — `grep -qiE 'source of record|one compliance|azqr.*compliance' snapshot.md && echo OK || echo MISSING`
- [ ] read-only / no-mutation: the output asserts NO mutations were performed and lists ONLY az MCP read tools (`subscription_list`, `group_resource_list`, `extension_azqr`, `resourcehealth`, `policy`, `role`) — `grep -qiE 'read-only|no mutation|performed no' snapshot.md && echo OK || echo MISSING`
- [ ] enforcement boundary stated honestly: the report names the real gate (Azure Policy `deny` effects + CI required-checks + branch-protection), labels Azure Policy `audit` effects as advisory/reporting-only and NOT part of the gate, and says the audit itself blocks/changes nothing — `grep -qiE 'deny.*(ci|branch)|branch.protection' snapshot.md && grep -qiE 'audit.*(advisory|report|log|not part|blocks nothing)' snapshot.md && echo OK || echo MISSING`
- [ ] cross-refs the siblings as the owners of the excluded jobs — `azure-waf` for pillar SCORING and `azure-cost` for the cost backlog — and does not reimplement either: `grep -qE 'azure-waf' snapshot.md && grep -qE 'azure-cost' snapshot.md && echo OK || echo MISSING`
- [ ] refuses (no fabricated snapshot) when no live subscription is reachable, or when `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` · `command -v azqr` (the azqr extension) · az MCP reachable and a subscription resolves via `subscription_list` → note absent, don't fail

## Functional
- Run the skill against a live (or sandbox) subscription: the `azqr` report path opens, a sampled azqr finding resolves to a real resource, and the resource-health state plus the azqr compliance verdict (with its policy-effect annotation) for that resource match what the Azure portal shows — confirm there is no second, separately-derived compliance section that could disagree. Confirm the subscription is unchanged afterward (read-only) and that the snapshot defers scoring to `azure-waf` and the cost backlog to `azure-cost`.
