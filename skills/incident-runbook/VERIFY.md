# VERIFY — incident-runbook

Run after `incident-runbook` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] an OE:08 incident-response plan exists naming the 3 roles + escalation/comms structure: `grep -rEqi 'incident manager|technical lead|communications lead' . && grep -rEqi 'escalat|on-call|severity' . && echo OK || echo MISSING`
- [ ] the plan documents detect → triage → contain → recover procedures with entry/exit criteria, referencing `obs_backend` signals (not re-defined here): `grep -rEqi 'detect|triage|contain|recover' . && echo OK || echo MISSING`
- [ ] recovery-playbook automations present (Azure Automation Runbooks / Functions / Logic Apps) + recovery/validation/RCA scripts: `grep -rEqi 'runbook|logic app|azure function|validation|rca' . && echo OK || echo MISSING`
- [ ] (profile-driven) automations match `platform` in `org-profile.yaml` (`aks`/`webapp` recovery targets) — no wrong-platform recovery primitive; plan names REAL on-call owners, not placeholders

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` (`az automation` / `az functionapp`) → note absent, don't fail (plan is advisory docs + tooling)

## Functional
- Each automation runs against a non-prod target and its post-recovery validation step passes; the named on-call owners are real, not TBD.
