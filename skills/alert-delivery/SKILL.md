---
name: alert-delivery
description: Use when you need to WIRE existing alert rules to a real notification channel so a firing alert reaches a human — "where does the alert go", "set up the action group / Alertmanager receiver", "page us on Teams/PagerDuty", "configure email/SMS/webhook on alert". NOT for authoring the alert rules or SLOs (observability-gen owns those) and NOT for naming on-call owners or recovery steps (incident-runbook). Reads org-profile.yaml platform + obs_backend; refuses if either is unset or if asked to author the rules themselves.
---

# Alert Delivery

## When to use
- "wire the alert to a receiver", "set up the action group", "configure the Alertmanager receiver/routing"
- A rule authored by `observability-gen` exists but nothing connects it to a channel — "the alert fires but nobody gets paged"
- "send alerts to email/SMS/webhook/Teams/Logic App" (App Service) or "page PagerDuty/Opsgenie" (k8s)
- You need grouping / inhibition / repeat_interval on a Prometheus routing tree

## When NOT to use
- Authoring the alert rule / SLI / SLO itself → `observability-gen` (this skill consumes the rule, it does not define it)
- Naming the on-call OWNER, escalation, or recovery steps → `incident-runbook`
- Storing the receiver's secret value (PD/Opsgenie key, webhook token) → `secrets`
- No declared `platform` or `obs_backend` → this skill refuses

## Inputs
- `org-profile.yaml` → `platform` — REQUIRED (selects action group vs Alertmanager)
- `org-profile.yaml` → `obs_backend` — REQUIRED (where the rules + metrics live)
- The alert rules already authored by `observability-gen` (the thing being wired)
- Receiver secrets (PD/Opsgenie integration key, webhook URL) referenced via `secrets`, never literal

## Steps
1. Read `org-profile.yaml`; resolve `platform` + `obs_backend`. If either is unset, REFUSE.
2. If asked to define the alert condition/threshold itself, REFUSE and route to `observability-gen`.
3. **`webapp` / App Service** → Azure Monitor **action group**: email/SMS/voice + webhook/Teams/Logic App receivers; bind the action group to the existing alert rule's actions.
4. **`aks` / `k8s` with Prometheus** → **Alertmanager** receivers + routing tree: `route` (group_by, group_wait, group_interval, repeat_interval), `inhibit_rules`, and receivers; pull receiver secrets from the `secrets` skill (no literal keys in the config).
5. Optional `PagerDuty`/`Opsgenie` receiver on either platform; integration key via `secrets`.
6. Record which rule maps to which receiver so the path rule → channel → human is discoverable.

## Output / validation
- An action group (webapp) OR Alertmanager receiver + routing tree (k8s) bound to the existing rules, with secrets referenced not inlined
- Verify: fire a test alert (Azure test action group / `amtool` test routing) and confirm it reaches the channel
- This is an advisory scaffold — the receiver config IS the real control; switching channel = config change, no rule edits

## Refuses when
- `platform` or `obs_backend` is unset in `org-profile.yaml`
- Asked to author/redefine the alert rule, SLI, or SLO (route to `observability-gen`)
- Asked to inline a receiver secret instead of referencing it via `secrets`

## Sources
- Azure Monitor action groups; Prometheus Alertmanager configuration (routing tree, receivers, inhibition)
