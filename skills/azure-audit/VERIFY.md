# VERIFY — azure-audit

Run after `azure-audit` has been applied to a live subscription. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the snapshot has all four sections grounded in real az MCP data — inventory, azqr findings, resource health, policy compliance — each finding carrying a real resource id: `grep -qiE 'inventor|azqr|resource health|policy complian' snapshot.md && echo OK || echo MISSING` (and every id resolves to a real resource, not a placeholder)
- [ ] read-only / no-mutation: the output asserts NO mutations were performed and lists ONLY az MCP read tools (`subscription_list`, `group_resource_list`, `extension_azqr`, `resourcehealth`, `policy`, `role`) — `grep -qiE 'read-only|no mutation|performed no' snapshot.md && echo OK || echo MISSING`
- [ ] enforcement boundary stated: the report names the real gate (Azure Policy `deny`/`audit` effects + CI required-checks) and says the audit itself blocks/changes nothing — `grep -qiE 'azure policy|deny|advisory|does not (block|enforce)' snapshot.md && echo OK || echo MISSING`
- [ ] cross-refs the siblings as the owners of the excluded jobs — `azure-waf` for pillar SCORING and `azure-cost` for the cost backlog — and does not reimplement either: `grep -qE 'azure-waf' snapshot.md && grep -qE 'azure-cost' snapshot.md && echo OK || echo MISSING`
- [ ] refuses (no fabricated snapshot) when no live subscription is reachable, or when `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` · `command -v azqr` (the azqr extension) · az MCP reachable and a subscription resolves via `subscription_list` → note absent, don't fail

## Functional
- Run the skill against a live (or sandbox) subscription: the `azqr` report path opens, a sampled azqr finding resolves to a real resource, and the resource-health + policy-compliance state for that resource matches what the Azure portal shows. Confirm the subscription is unchanged afterward (read-only) and that the snapshot defers scoring to `azure-waf` and the cost backlog to `azure-cost`.
