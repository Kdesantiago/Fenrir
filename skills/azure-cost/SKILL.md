---
name: azure-cost
description: Use when cutting LIVE Azure infra spend on a real subscription via the az MCP — pull actual cost + Advisor recs + retail pricing into a ranked, dollar-quantified right-size / idle / reservation backlog. Triggers — "analyze our Azure bill", "cut our Azure spend", "find idle Azure resources", "right-size this resource group". NOT LLM-API spend (llm-cost-monitor), NOT per-US token cost (us-cost-tracking), NOT cost-aware IaC (iac-gen). Advisory + read-only; gate is CI budget check / Azure Budgets. Reads org-profile.yaml `platform`; refuses without a live subscription.
---

# Azure Cost — live Azure FinOps

Pull **real** subscription spend, Advisor cost recommendations, and retail pricing from the **az MCP** and turn them into a ranked, dollar-quantified, low-risk-first optimization backlog (right-sizing, idle resources, reservations / savings plans). This skill is **advisory and READ-ONLY**: it PROPOSES and RECOMMENDS against a tenant it never mutates — the tenant stays the source of truth and the deterministic cost gate is a CI budget check / Azure Budgets + tagging policy, **not** this skill. Every backlog line cites a real resource id and a dollar figure that came back from the az MCP; it never estimates spend from memory.

## When to use
- "analyze our Azure bill", "where are we wasting Azure spend", "cut our Azure costs"
- "find idle Azure resources", "right-size this resource group", "should we buy reservations / a savings plan", "Azure FinOps"
- You have a live Azure subscription (or a `stack-interface.yaml` wrapper) and want a costed optimization backlog, not generated IaC

## When NOT to use
- LLM / model **API** spend (per-route/per-model token cost, budgets, anomaly alerts) → `llm-cost-monitor` (different cost axis — cross-ref, do not reimplement)
- Agent / subagent **token-cost** accounting against a User Story on the dashboard → `us-cost-tracking` (different cost axis — cross-ref, do not reimplement)
- Generating cost-aware **IaC** (SKUs, autoscale, plan tiers) → `iac-gen` (it emits files; this skill only reads + recommends)
- No live subscription / az MCP not connected → this skill **refuses** (it cannot fabricate spend)

## Inputs
- **az MCP (live read, advisory):** `mcp__azure__subscription_list` (confirm a reachable subscription), `mcp__azure__group_resource_list` (billable-resource inventory), `mcp__azure__advisor` (Cost-category recommendations: idle/underused, right-size, reservation candidates), `mcp__azure__pricing` (retail price book to quantify savings), and the per-service inventory/utilization tools for the declared platform scope — `mcp__azure__aks`, `mcp__azure__appservice`, `mcp__azure__compute`, `mcp__azure__storage` (plus `mcp__azure__functionapp` / `mcp__azure__containerapps` where relevant) for SKU + sizing + stopped-but-billed state.
- `org-profile.yaml` → `platform` — OPTIONAL, used to **focus** the scan on the resource types the org actually runs (`aks`/`k8s` → node pools + idle nodes; `webapp` → App Service plans + slots; `serverless` → consumption vs premium; `vm`/`ecs` → compute + disks). Without it, scan broadly and say so.
- `stack-interface.yaml` (OPTIONAL): when present, resolve subscription/login context via the **`stack-adapter`** agent; never emit raw `az` for the login/subscription-selection step.

## Steps
1. **Confirm a live subscription — never estimate.** Call `mcp__azure__subscription_list`; pick the target subscription (if `stack-interface.yaml` exists, get the login/subscription-selection commands from `stack-adapter`, do not emit raw `az`). If no subscription is reachable / the az MCP is not connected, **REFUSE** — fabricating spend is a defect.
2. **Inventory billable resources for the platform scope.** Read `org-profile.yaml` `platform` to focus the scan, then list resources with `mcp__azure__group_resource_list` and pull SKU + utilization from the per-service tools (`mcp__azure__compute`, `mcp__azure__aks`, `mcp__azure__appservice`, `mcp__azure__storage`, …). Capture each resource id, type, SKU/tier, region.
3. **Quantify with Advisor + retail pricing.** Pull Cost-category recommendations from `mcp__azure__advisor` (these carry Azure's own estimated savings and impacted resource ids) and look up retail rates with `mcp__azure__pricing` to confirm/derive the dollar delta for each candidate. Every number is sourced from the MCP — cite where it came from (advisor vs pricing).
4. **Detect idle / underutilized + reservation candidates.** From the inventory + utilization: stopped-but-still-billed resources (deallocated VMs left on a billed disk, idle AKS node pools), low-utilization SKUs (oversized VM/App Service plan), orphaned disks/public IPs/NIC-less NSGs, and steady-state workloads that are reservation / savings-plan candidates (1yr/3yr break-even from pricing). Tag each with a **confidence** (high = Advisor-backed + pricing-reconciled; medium = utilization-inferred; low = needs human sizing).
5. **Emit the prioritized FinOps backlog.** Produce advisory text, ordered **lowest-risk-first then by dollar savings** (delete-orphan / stop-billed before resize before buy-reservation), using the Output contract below. This is a recommendation list, not an enforced budget.
6. **State the boundary, loudly.** Close every report with: this skill is advisory and read-only — it recommends, it does not block; the deterministic cost gate is a **CI budget check / Azure Budgets + a tagging/cost policy** (Azure Policy), wired separately. Implementing the resizes is a change (route through `iac-gen` for cost-aware IaC + the normal delivery gates), not something this skill applies.

## Output / validation
- A ranked **FinOps backlog** where every line is: `resource id · type/SKU · region · current monthly cost · recommended action · est. monthly savings · confidence · source (advisor|pricing)`, ordered low-risk-first then by savings, with a subscription-level total.
- Validate: the top item resolves to a **real** resource id returned by the inventory call, and its savings estimate reconciles against `mcp__azure__pricing` (or the Advisor figure). No placeholder ids, no from-memory numbers.
- Reiterate the boundary: this is advice on a live, read-only pull. The tenant is the source of truth; the cost **gate** is CI Budget check / Azure Budgets + policy, not this skill. Cross-refs `llm-cost-monitor` (LLM-API spend) and `us-cost-tracking` (agent-token spend) as the owners of those other cost axes — no overlap claimed here.

## Refuses when
- No live subscription is reachable / the az MCP is not connected (`mcp__azure__subscription_list` returns nothing) — cannot fabricate spend.
- Asked to **estimate** Azure spend from memory / generic pricing instead of pulling real cost from the az MCP.
- Asked to MUTATE the subscription (delete/resize/buy a reservation) — this skill is read-only/advisory; route the change through `iac-gen` + delivery gates.
- Asked to cover LLM-API spend (→ `llm-cost-monitor`) or agent/per-US token cost (→ `us-cost-tracking`) — different cost axes, owned by those siblings.
- Asked to be presented as a hard cost gate that blocks merges/spend — it is advisory; the gate is a CI budget check / Azure Budgets + policy.
