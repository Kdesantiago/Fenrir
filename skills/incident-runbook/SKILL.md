---
name: incident-runbook
description: Use when you need an incident-response PLAN and a RECOVERY-PLAYBOOK for a running service — roles, escalation/comms structure, detection/triage/containment/recovery procedures, plus generated Azure Automation Runbooks / Functions / Logic Apps automations and a recovery+validation+RCA script library for the AKS/App Service stack. NOT for writing the alert rules themselves (observability-gen). Reads org-profile.yaml `platform` + `obs_backend` and refuses without `platform`.
---

# Incident Runbook

## When to use
- "write the incident-response plan", "who is incident manager / tech lead / comms lead"
- "generate the recovery playbook / automation runbooks" for this service
- You have signals firing and need a documented triage → contain → recover → RCA path

## When NOT to use
- Defining the alert rules / SLI signals that page you → use `observability-gen`
- Watching a live rollout for regressions → use the `aks-deploy-watch` Monitor (`monitors/`)
- No declared `platform` → this skill refuses (it cannot pick the automation primitive)

## Inputs
- `org-profile.yaml` → `platform` (REQUIRED — `aks`/`webapp` select the recovery automation targets) and `obs_backend` (where detection/triage signals come from)
- Existing alert/signal definitions from `observability-gen` (consumed, not authored here)

## Steps
1. Read `org-profile.yaml`; resolve `platform`. If unset, REFUSE.
2. Generate the incident-response PLAN per Azure WAF **OE:08**:
   - Roles: incident manager (drives), technical lead (diagnoses/fixes), communications lead (stakeholder + status updates).
   - Communication + escalation structure: who is paged, when it escalates, who declares severity, status-page/comms cadence.
   - Procedures: detection → triage → containment → recovery, each with entry/exit criteria. Detection/triage reference `obs_backend` signals (authored by `observability-gen`), never re-defined here.
3. Generate the RECOVERY-PLAYBOOK automations, scoped by `platform`:
   - `aks` / `webapp` → Azure Automation Runbooks / Functions / Logic Apps for the common recovery actions (restart/roll back deployment, scale, drain node, failover, clear cache).
   - A script library: recovery scripts + post-recovery **validation** checks + an **RCA** template/data-collection script.
4. Optionally reference Azure SRE Agent **incident-response-plans** for filter-based routing (route an incident to the right plan by signal/resource filters).
5. State explicitly that this plan/playbook is ADVISORY documentation + tooling; it does not enforce anything.

## Output / validation
- An OE:08 incident-response plan (roles, comms/escalation, detect/triage/contain/recover) + a `platform`-correct recovery playbook (runbooks/functions/logic apps + recovery/validation/RCA scripts)
- Verify each automation runs against a non-prod target and its validation step passes; verify the plan names real on-call owners
- The plan is a runbook, not a control: actual recovery is performed by the named automations and on-call humans, not by this skill

## Refuses when
- `org-profile.yaml` is missing, or `platform` is unset
- Asked to author the alert rules / SLI signals (route to `observability-gen`)
- Asked to emit recovery automations for a `platform` it does not support (only `aks`/`webapp` recovery targets are generated)

## Sources
- https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/incident-response
- https://learn.microsoft.com/en-us/azure/sre-agent/incident-response-plans
