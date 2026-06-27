# VERIFY — cronjob

Run after `cronjob` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the scheduled-job manifest matches the declared `platform` (the right primitive, no wrong one): `aks`/`k8s` → Kubernetes `CronJob`; `webapp`/`serverless` → Functions timer (NCRONTAB) / Container Apps job; `vm` → systemd timer; `ecs` → EventBridge→ECS — emitted file exists and is the correct kind
- [ ] reliability defaults ALL set (this is the point): no-double-run (`concurrencyPolicy: Forbid|Replace` / singleton), timeout (`activeDeadlineSeconds`/function timeout), bounded `backoffLimit`, `startingDeadlineSeconds`, and history limits — grep the manifest to confirm each is present
- [ ] timezone stated explicitly (k8s `spec.timeZone` / `WEBSITE_TIME_ZONE`), not silently UTC; cron expression parses; idempotency strategy is stated in the runbook
- [ ] failure alert AND missed-run detector wired via `obs_backend` (e.g. `job_last_success_timestamp` overdue alert for prometheus); secrets pulled from the store, no inline env literals

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v kubectl` · `command -v helm` · `command -v az` · `command -v func` (per platform) → note absent, don't fail

## Functional
- The cron expression parses and the manifest validates for its target (`kubectl apply --dry-run=server` for k8s / `systemd-analyze verify` for the unit / NCRONTAB parses); the runbook lists the next 3 run times and where the failure alert fires.
