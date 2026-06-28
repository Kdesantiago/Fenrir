---
name: azure-waf
description: Use when SCORING a LIVE Azure subscription against the 5 Well-Architected pillars via the az MCP — a per-pillar scored report + severity-ranked remediation backlog grounded in real resource findings. Triggers — "run a WAF review", "Well-Architected assessment", "score our Azure pillars". NOT for DESIGNING a system / WAF-pillar ADR (azure-architect), NOT the inventory snapshot (azure-audit, which it consumes), NOT cost backlog (azure-cost). Advisory + read-only; gate is Azure Policy + CI. Reads org-profile.yaml `platform`/`obs_backend`; refuses without a live subscription.
---

# Azure WAF — live Well-Architected pillar scoring

Score a LIVE Azure subscription against the **5 Well-Architected pillars** (reliability, security, cost, operational excellence, performance) through the **az MCP**, producing a per-pillar scored report plus a severity-ranked remediation backlog. This skill **operates a live subscription** via the az MCP and is **advisory + READ-ONLY**: it PROPOSES a score and RECOMMENDS fixes against a tenant it never mutates. The deterministic gate is **Azure Policy `deny`/`audit` effects + CI required-checks + branch-protection**, never this skill — a WAF score cannot stop a non-compliant resource from existing, it can only grade it. It is the **scoring/synthesis layer**: it consumes the raw posture from `azure-audit` and the cost numbers from `azure-cost` rather than re-querying them, and every pillar score is grounded in at least one live-resource finding (a real resource id + Advisor/WAF recommendation), never generic WAF prose from memory.

## When to use
- "run a Well-Architected review", "WAF assessment", "score our Azure across the 5 pillars"
- "reliability/security/cost/operational/performance review of our live resources"
- You want a pillar-scored architecture assessment of a running subscription, not generic guidance

## When NOT to use
- DESIGNING a new architecture / writing a WAF-pillar ADR for a new system → `azure-architect` agent (it DECIDES and records an Azure ADR grounded in live state + WAF guidance; this skill GRADES an existing live tenant)
- The raw resource inventory + `azqr` quick-review + health/policy-compliance snapshot → `azure-audit` (this skill CONSUMES that snapshot as its evidence base; it does not re-run the inventory)
- A standalone costed right-sizing / idle / reservation backlog → `azure-cost` (the WAF **cost pillar** cross-refs it for the dollar numbers; do not reimplement the FinOps backlog here)
- Generating the IaC / policy that fixes a finding → `iac-gen` (file emitter; this skill only reads live state and recommends)
- Live incident triage / root-cause on a running service → `azure-sre` (operate-during-incident, not a posture grade)

## Inputs
- **az MCP (live, read-only)** — the score is built entirely from these tools:
  - `mcp__azure__subscription_list` → confirm a reachable subscription (refuse if none)
  - `mcp__azure__group_resource_list` → the live resource posture each pillar is scored against
  - `mcp__azure__wellarchitectedframework` → the official per-pillar WAF guidance / recommendations to score against
  - `mcp__azure__advisor` → live Advisor recommendations, mapped to their pillar (Reliability / Security / Cost / Operational Excellence / Performance categories map 1:1 onto the WAF pillars)
  - `mcp__azure__resourcehealth` → availability / service-health evidence for the reliability pillar
- `org-profile.yaml` → `platform` + `obs_backend` (OPTIONAL focus) — `platform` scopes which resource types to weight; `obs_backend` informs the reliability + operational-excellence pillars (is telemetry/alerting actually wired). Absence does not block the score, but a wrong/non-Azure value is noted.
- `stack-interface.yaml` (OPTIONAL) → when present, resolve subscription/login context through the `stack-adapter` agent; never emit raw `az login` / `az account set`.
- **Sibling snapshots (preferred evidence):** if an `azure-audit` snapshot or `azure-cost` backlog already exists, consume them as the evidence base instead of re-querying — cite them.

## Steps
1. **Confirm a live subscription is reachable.** Call `mcp__azure__subscription_list`. If nothing resolves (az MCP not connected / no auth / no subscription), **REFUSE** — never fabricate a pillar score or invent resource ids. If `stack-interface.yaml` exists, resolve login/subscription context via `stack-adapter` first (embed verbatim; on `MISSING-MAPPING`, stop).
2. **Establish the evidence base.** Prefer an existing `azure-audit` snapshot (inventory + azqr + health + policy) and `azure-cost` backlog; otherwise pull the live posture via `mcp__azure__group_resource_list` (+ `mcp__azure__resourcehealth` for availability). Read `org-profile.yaml` `platform`/`obs_backend` to weight the scope. Do NOT re-implement the audit or the cost backlog — cite the sibling.
3. **Per pillar, pull WAF guidance + map live findings.** For each of the 5 pillars (reliability, security, cost, operational excellence, performance), pull the pillar's guidance from `mcp__azure__wellarchitectedframework` and map the live `mcp__azure__advisor` recommendations onto it by Advisor category (Reliability/Security/Cost/OperationalExcellence/Performance → the matching pillar). Attach each mapped finding's real resource id + severity. For the **cost pillar**, pull the dollar figures from `azure-cost` (cross-ref) rather than re-deriving them.
4. **Score each pillar against the live posture.** Assign each pillar a score on a consistent scale (e.g. 1–5 or Red/Amber/Green) with a one-line rationale, and capture the evidence behind the score: at least one `resource id + finding` per pillar. No pillar is scored from generic WAF prose alone — a score with no live-resource evidence is a defect.
5. **Emit the scored report + remediation backlog.** Produce (a) a per-pillar table (pillar · score · rationale · top evidence) and (b) a severity-ranked remediation backlog where every item references a real resource and the pillar it raises. Use the Output contract below. Order the backlog by severity then pillar impact.
6. **State the boundary, loudly.** Close by asserting this skill is advisory + read-only — it scores and recommends, it changed nothing and blocks nothing. The deterministic gate is Azure Policy `deny`/`audit` effects + CI required-checks + branch-protection; remediation is delivered by `iac-gen` + the normal delivery gates. List exactly which az MCP read tools were used.

## Output / validation
- A **scored report**: all 5 pillars present, each with a score + rationale + at least one live-resource-grounded finding (a real resource id from the az MCP), plus a **severity-ranked remediation backlog** where each line is `severity · pillar · resource id · finding · recommended action · source (waf|advisor|azure-cost)`.
- Validation: every resource id in the report resolves to a real resource; each pillar score reconciles with the underlying `mcp__azure__advisor` / `mcp__azure__wellarchitectedframework` findings it cites; the report names the specific resources scored. No placeholder ids, no from-memory scores.
- Cross-refs reiterated: the **cost pillar** cross-refs `azure-cost` for dollar numbers and the evidence base cross-refs `azure-audit` for inventory — neither is reimplemented here.
- Boundary reiterated: this skill **advises**, it does not enforce. Azure Policy `deny`/`audit` effects + CI required-checks + branch-protection are the deterministic gate — a WAF score never blocks or changes a resource.

## Refuses when
- No live subscription is reachable via the az MCP (`mcp__azure__subscription_list` returns nothing / not connected / unauthenticated) — refuse rather than fabricate a pillar score, a resource id, or an Advisor finding.
- `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING` for the login/subscription op — stop; do not fall back to a raw `az` command.
- Asked to produce a pillar score with no live-resource evidence (generic WAF prose only) — every score must cite at least one real finding; refuse to grade from memory.
- Asked to MUTATE the subscription (remediate a finding, change a resource) — out of scope; this skill is read-only, route remediation to `iac-gen` + delivery gates and enforcement to Azure Policy.
- Asked to DESIGN a new system / write a WAF-pillar ADR (`azure-architect`), re-run the raw inventory snapshot (`azure-audit`), or produce the standalone cost backlog (`azure-cost`) — route to the named sibling.
- Asked to be presented as a hard gate that blocks merges — it is advisory; the gate is Azure Policy + CI required-checks + branch-protection.
