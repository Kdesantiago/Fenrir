---
name: azure-waf
description: Use when SCORING a LIVE Azure subscription against the 5 Well-Architected pillars via the az MCP — a per-pillar scored report + severity-ranked remediation backlog grounded in real findings (advisor + resourcehealth + inventory). Triggers — "run a WAF review", "Well-Architected assessment", "score our Azure pillars". NOT for DESIGNING a system / WAF-pillar ADR (azure-architect), NOT the inventory snapshot (azure-audit, preferred evidence), NOT cost backlog (azure-cost). Advisory + read-only; gate is Azure Policy + CI. Refuses without a live subscription.
---

# Azure WAF — live Well-Architected pillar scoring

Score a LIVE Azure subscription against the **5 Well-Architected pillars** (reliability, security, cost, operational excellence, performance) through the **az MCP**, producing a per-pillar scored report plus a severity-ranked remediation backlog. This skill **operates a live subscription** via the az MCP and is **advisory + READ-ONLY**: it PROPOSES a score and RECOMMENDS fixes against a tenant it never mutates. The deterministic gate is **Azure Policy `deny`/`audit` effects + CI required-checks + branch-protection**, never this skill — a WAF score cannot stop a non-compliant resource from existing, it can only grade it. It is the **scoring/synthesis layer**, and it is honest about where each pillar score comes from: `mcp__azure__wellarchitectedframework` supplies the **generic, per-service WAF RUBRIC** (static best-practice guidance keyed only by `Service` — it reads NO live tenant state), while the **live EVIDENCE that actually moves the score comes solely from `mcp__azure__advisor` + `mcp__azure__resourcehealth` + the resource inventory**. It PREFERS the `azure-audit` snapshot and `azure-cost` backlog as its evidence base; when no `azure-audit` snapshot exists it OWNS a minimal inventory pull (`group_resource_list` + `resourcehealth`) explicitly rather than pretending it never queries. Every pillar score is grounded in at least one live-resource finding (a real resource id + Advisor/resource-health evidence, scored against the WAF rubric), never generic WAF prose alone.

## When to use
- "run a Well-Architected review", "WAF assessment", "score our Azure across the 5 pillars"
- "reliability/security/cost/operational/performance review of our live resources"
- You want a pillar-scored architecture assessment of a running subscription, not generic guidance

## When NOT to use
- DESIGNING a new architecture / writing a WAF-pillar ADR for a new system → `azure-architect` agent (it DECIDES and records an Azure ADR grounded in live state + WAF guidance; this skill GRADES an existing live tenant)
- The raw resource inventory + `azqr` quick-review + health/policy-compliance snapshot → `azure-audit` (this skill PREFERS that snapshot as its evidence base and does not re-run the full `azqr` audit; but when no snapshot exists it OWNS a minimal `group_resource_list` + `resourcehealth` pull to ground the scores — it does not pretend the inventory is never queried)
- A standalone costed right-sizing / idle / reservation backlog → `azure-cost` (the WAF **cost pillar** cross-refs it for the dollar numbers; do not reimplement the FinOps backlog here)
- Generating the IaC / policy that fixes a finding → `iac-gen` (file emitter; this skill only reads live state and recommends)
- Live incident triage / root-cause on a running service → `azure-sre` (operate-during-incident, not a posture grade)

## Inputs
- **az MCP (live, read-only)** — the LIVE evidence comes from `advisor` + `resourcehealth` + the resource inventory; the WAF tool only supplies the static rubric:
  - `mcp__azure__subscription_list` → confirm a reachable subscription (refuse if none)
  - `mcp__azure__group_resource_list` → the live resource posture each pillar is scored against
  - `mcp__azure__wellarchitectedframework` → the generic, per-service WAF **rubric** to score against (takes only a `Service` param, e.g. 'App Service'/'Cosmos DB'; returns static best-practice guidance — READ-ONLY, it does NOT take a subscription/resource scope and reads NO live tenant state). This is the scoring criteria, NOT live evidence.
  - `mcp__azure__advisor` → live Advisor recommendations, mapped to their pillar (Reliability / Security / Cost / Operational Excellence / Performance categories map 1:1 onto the WAF pillars)
  - `mcp__azure__resourcehealth` → availability / service-health evidence for the reliability pillar
- `org-profile.yaml` → `platform` + `obs_backend` (OPTIONAL focus) — `platform` scopes which resource types to weight; `obs_backend` informs the reliability + operational-excellence pillars (is telemetry/alerting actually wired). Absence does not block the score, but a wrong/non-Azure value is noted.
- `stack-interface.yaml` (OPTIONAL) → when present, resolve subscription/login context through the `stack-adapter` agent; never emit raw `az login` / `az account set`.
- **Sibling snapshots (preferred evidence):** if an `azure-audit` snapshot or `azure-cost` backlog already exists, consume them as the evidence base instead of re-querying — cite them.

## Steps
1. **Confirm a live subscription is reachable.** Call `mcp__azure__subscription_list`. If nothing resolves (az MCP not connected / no auth / no subscription), **REFUSE** — never fabricate a pillar score or invent resource ids. If `stack-interface.yaml` exists, resolve login/subscription context via `stack-adapter` first (embed verbatim; on `MISSING-MAPPING`, stop).
2. **Establish the evidence base.** Prefer an existing `azure-audit` snapshot (inventory + azqr + health + policy) and `azure-cost` backlog — cite them. If no snapshot exists, this skill OWNS a minimal inventory pull via `mcp__azure__group_resource_list` (+ `mcp__azure__resourcehealth` for availability) to ground the scores — this is an explicit, declared overlap with `azure-audit`'s inventory step, not a hidden one. Do NOT re-implement the full `azqr` audit or the cost backlog; keep the pull minimal and cite the sibling whenever one exists.
3. **Per pillar, pull the WAF rubric + map live findings.** For each of the 5 pillars (reliability, security, cost, operational excellence, performance), pull the relevant per-service **rubric** from `mcp__azure__wellarchitectedframework` (generic best-practice criteria, no live state) and map the live `mcp__azure__advisor` recommendations onto it by Advisor category (Reliability/Security/Cost/OperationalExcellence/Performance → the matching pillar). The Advisor findings + `resourcehealth` are the live evidence; the WAF rubric is only the yardstick. Attach each mapped finding's real resource id + severity. For the **cost pillar**, pull the dollar figures from `azure-cost` (cross-ref) rather than re-deriving them.
4. **Score each pillar against the live posture.** Assign each pillar a score on a consistent scale (e.g. 1–5 or Red/Amber/Green) with a one-line rationale, and capture the evidence behind the score: at least one `resource id + finding` per pillar. No pillar is scored from generic WAF prose alone — a score with no live-resource evidence is a defect.
5. **Emit the scored report + remediation backlog.** Produce (a) a per-pillar table (pillar · score · rationale · top evidence) and (b) a severity-ranked remediation backlog where every item references a real resource and the pillar it raises. Use the Output contract below. Order the backlog by severity then pillar impact.
6. **State the boundary, loudly.** Close by asserting this skill is advisory + read-only — it scores and recommends, it changed nothing and blocks nothing. The deterministic gate is Azure Policy `deny`/`audit` effects + CI required-checks + branch-protection; remediation is delivered by `iac-gen` + the normal delivery gates. List exactly which az MCP read tools were used.

## Output / validation
- A **scored report**: all 5 pillars present, each with a score + rationale + at least one live-resource-grounded finding (a real resource id from the az MCP), plus a **severity-ranked remediation backlog** where each line is `severity · pillar · resource id · finding · recommended action · source (waf|advisor|azure-cost)`.
- Validation: every resource id in the report resolves to a real resource; each pillar score reconciles with the underlying LIVE `mcp__azure__advisor` + `mcp__azure__resourcehealth` findings it cites, scored against the static `mcp__azure__wellarchitectedframework` rubric (the rubric is the criteria, not live evidence); the report names the specific resources scored. No placeholder ids, no from-memory scores.
- Cross-refs reiterated: the **cost pillar** cross-refs `azure-cost` for dollar numbers and the evidence base cross-refs `azure-audit` for inventory — neither is reimplemented here.
- Boundary reiterated: this skill **advises**, it does not enforce. Azure Policy `deny`/`audit` effects + CI required-checks + branch-protection are the deterministic gate — a WAF score never blocks or changes a resource.

## Refuses when
- No live subscription is reachable via the az MCP (`mcp__azure__subscription_list` returns nothing / not connected / unauthenticated) — refuse rather than fabricate a pillar score, a resource id, or an Advisor finding.
- `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING` for the login/subscription op — stop; do not fall back to a raw `az` command.
- Asked to produce a pillar score with no live-resource evidence (generic WAF prose only) — every score must cite at least one real finding; refuse to grade from memory.
- Asked to MUTATE the subscription (remediate a finding, change a resource) — out of scope; this skill is read-only, route remediation to `iac-gen` + delivery gates and enforcement to Azure Policy.
- Asked to DESIGN a new system / write a WAF-pillar ADR (`azure-architect`), re-run the raw inventory snapshot (`azure-audit`), or produce the standalone cost backlog (`azure-cost`) — route to the named sibling.
- Asked to be presented as a hard gate that blocks merges — it is advisory; the gate is Azure Policy + CI required-checks + branch-protection.
