---
name: azure-audit
description: Use when auditing a LIVE Azure subscription via the az MCP — inventory + azqr quick-review + resource health + policy compliance + RBAC in one read-only snapshot. Triggers — "audit our Azure subscription", "run azqr", "policy compliance scan", "are any resources unhealthy". NOT for WAF pillar scoring (azure-waf, which consumes this), NOT the cost backlog (azure-cost), NOT SAST/SBOM on a diff (security-review). Read-only/advisory — the gate is Azure Policy deny + CI + branch-protection, never this skill. Reads org-profile.yaml `platform`; refuses without a live subscription.
---

# Azure Audit — live subscription posture snapshot

A current-state, **read-only** posture snapshot of a LIVE Azure subscription, taken through the az MCP: resource inventory + `azqr` quick-review (the compliance **source of record**) + resource health + RBAC, in one report. It **operates a live subscription** via the az MCP and is **advisory** — it PROPOSES findings, it does not remediate. The deterministic gate is Azure Policy `deny` effects + CI required-checks + branch-protection, never this skill: an audit cannot stop a non-compliant resource from existing, it can only report it. Azure Policy `audit` effects are NOT part of that gate — `audit` only logs/reports a violation, it blocks nothing; this skill treats `audit` as advisory signal, the same as its own findings. Every line of the snapshot is grounded in a real resource id from a live az MCP call — nothing is fabricated from memory.

## When to use
- "audit our Azure subscription", "what's running in this tenant", "run azqr", "policy compliance scan", "are any resources unhealthy", "resource inventory"
- You want a current-state, read-only posture snapshot of a live subscription / resource group

## When NOT to use
- Scoring the posture against the 5 WAF pillars → `azure-waf` (it CONSUMES this audit's inventory; this skill does not score)
- A costed right-sizing / idle-resource / reservation backlog → `azure-cost` (cost axis; cross-ref, do not reimplement)
- SAST / SBOM / threat-check on a code diff → `security-review` (code, not a live tenant)
- Generating policy / landing-zone / IaC files → `iac-gen` (file emitter; this skill only reads live state)

## Inputs
- **az MCP (live, read-only)** — the snapshot is built entirely from these tools:
  - `mcp__azure__subscription_list` + `mcp__azure__group_resource_list` → the resource inventory
  - `mcp__azure__extension_azqr` → the Azure Quick Review (azqr) report — this is the **compliance source of record** (its `Azure Policy` sheet / `--stages policy` already reports Policy non-compliance, plus Advisor recommendations)
  - `mcp__azure__resourcehealth` → availability + active service-health events per resource
  - `mcp__azure__policy` → ONLY for assignment/effect metadata that azqr does NOT surface (e.g. which assignments carry a `deny` vs `audit` effect, scope, exemptions) — NOT a second per-resource compliance verdict; azqr owns the compliance state
  - `mcp__azure__role` → RBAC assignments for the access-posture note
- `org-profile.yaml` → `platform` (OPTIONAL) — scopes which resource types to focus the inventory on; absence does not block, but a wrong/non-Azure value is noted
- `stack-interface.yaml` (OPTIONAL) → when present, resolve subscription/login context through the `stack-adapter` agent; never emit raw `az login` / `az account set`

## Steps
1. **Confirm a live subscription is reachable.** Call `mcp__azure__subscription_list`. If nothing resolves (az MCP not connected / no auth / no subscription), **REFUSE** — never fabricate an inventory or invent resource ids. If `stack-interface.yaml` exists, resolve login/subscription context via `stack-adapter` first (embed verbatim; on `MISSING-MAPPING`, stop).
2. **Build the resource inventory.** Enumerate via `mcp__azure__group_resource_list` across the in-scope resource groups (focus on `org-profile.yaml` `platform` resource types when declared, e.g. AKS / App Service / storage). Record each resource id, type, location, and RG — this is the spine the other sections hang off.
3. **Run the azqr quick-review — the compliance source of record.** Invoke `mcp__azure__extension_azqr` for the Azure Quick Review report; capture each recommendation with its resource id, category, and severity, AND its `Azure Policy` non-compliance sheet (`--stages policy`). This single azqr snapshot is the ONE compliance verdict the report carries — do not produce a second, separately-derived compliance view that could disagree with it. Note the report path so a reviewer can re-open it.
4. **Pull resource health.** For the inventoried resources call `mcp__azure__resourcehealth`; flag any `Unavailable`/`Degraded` resource and any active platform service-health event (so a real Azure outage is not misread as a self-inflicted problem).
5. **Enrich the azqr compliance findings with effect metadata (no second verdict).** Call `mcp__azure__policy` ONLY to annotate the azqr-reported non-compliance with assignment metadata azqr does not surface — for each relevant assignment, its effect (`deny` vs `audit` vs `disabled`), scope, and any exemption. Do NOT re-derive a parallel per-resource compliance state; azqr (Step 3) owns the compliance verdict and this step only labels it. Flag each finding whose assignment effect is `deny` (it can be gated) versus `audit` (advisory/reporting only — it logs but blocks nothing).
6. **Summarize RBAC posture.** Call `mcp__azure__role` and note access risks (e.g. subscription-scope `Owner`/`Contributor` count, classic admins, stale/over-broad assignments) — a posture note, not a full identity audit.
7. **Emit the consolidated snapshot.** One report with THREE mandatory sections — **Inventory**, **azqr findings** (compliance source of record: azqr recommendations + its Azure Policy non-compliance, each annotated with the Step-5 effect metadata) and **Resource health** — plus the RBAC note; each finding carries its real resource id and a severity. There is exactly ONE compliance view (azqr's) so the report cannot contradict itself. Cross-ref `azure-waf` for pillar SCORING and `azure-cost` for the cost backlog; do not duplicate either.
8. **State the boundary.** Close by asserting the snapshot is read-only and advisory: it changed nothing and blocks nothing — remediation is delivered by other skills / IaC, and the gate is Azure Policy `deny` effects + CI required-checks + branch-protection. Azure Policy `audit` effects are advisory/reporting only and are NOT part of that gate. List exactly which az MCP read tools were used.

## Output / validation
- A single posture snapshot containing the three sections (inventory, azqr findings — which carry the one compliance verdict, annotated with policy-effect metadata — resource health) + an RBAC posture note, every finding tagged with its **real resource id** (from az MCP) and a severity, plus cross-refs to `azure-waf` and `azure-cost`. There is exactly one compliance view (azqr's); no separate, possibly-conflicting compliance section.
- Validation: every resource id in the snapshot resolves to a real resource; the `azqr` report path opens; a sampled health state and the azqr compliance verdict match the Azure portal. The output explicitly lists the read-only az MCP tools used and asserts NO mutations were performed.
- Boundary reiterated: this skill **advises**, it does not enforce. The deterministic gate is Azure Policy `deny` effects + CI required-checks + branch-protection — Azure Policy `audit` effects only log and are NOT part of the gate; a snapshot never blocks or changes a resource.

## Refuses when
- No live subscription is reachable via the az MCP (`subscription_list` returns nothing / not connected / unauthenticated) — refuse rather than fabricate inventory, health, or compliance.
- `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING` for the login/subscription op — stop; do not fall back to a raw `az` command.
- Asked to MUTATE the subscription (delete a resource, remediate a policy, change an RBAC assignment) — out of scope; this skill is read-only, route remediation to the owning skill / IaC and to Azure Policy for enforcement.
- Asked to SCORE against WAF pillars (`azure-waf`), produce a cost backlog (`azure-cost`), or scan a code diff (`security-review`) — route to the named sibling.
