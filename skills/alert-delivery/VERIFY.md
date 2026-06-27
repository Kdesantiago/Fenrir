# VERIFY — alert-delivery

Run after `alert-delivery` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] a receiver/channel is wired and BOUND to an existing alert rule (not a free-floating config): `webapp` → an Azure Monitor action group referenced by the rule's actions; `aks`/`k8s` → an Alertmanager receiver referenced by the routing tree
- [ ] the wiring matches `org-profile.yaml` `platform` (action group for webapp/App Service; Alertmanager receivers + routing tree for aks/k8s) and points at the `obs_backend` where the rules live
- [ ] for Alertmanager: the routing tree sets grouping (`group_by`/`group_wait`/`group_interval`), `repeat_interval`, and `inhibit_rules` — not a bare receiver with no routing
- [ ] NO alert rule / SLI / SLO is (re)defined here — those come from `observability-gen`; this skill only connects rule → receiver
- [ ] receiver secrets (PagerDuty/Opsgenie integration key, webhook token) are REFERENCED via `secrets`, never literal: `! grep -rEi '(integration_key|routing_key|webhook).*["'\''][A-Za-z0-9]{16,}["'\'']' <generated-dir>`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v amtool` (Alertmanager config check) · `command -v az` (action group test) → note absent, don't fail

## Functional
- Fire a test alert and confirm it reaches the channel: Azure test action group (webapp), or `amtool config routes test` / a test alert through Alertmanager (k8s). Switching the channel should be a config change only — no edits to the underlying alert rule.
