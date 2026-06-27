---
name: cronjob
description: Use when scheduling a recurring/periodic job — generates the platform-correct scheduled-job definition with the reliability defaults that a naked cron lacks (no double-run, no silent death, idempotent). Triggers — "schedule a job", "cron", "nightly/hourly batch", "recurring task", "Kubernetes CronJob", "timer-triggered function". NOT for event-driven triggers (queue/webhook/blob), NOT for one-off scripts, NOT for long-running services. Reads org-profile.yaml `platform`.
---

# Cronjob

A schedule is the easy 5%. The skill's job is the other 95%: pick the right platform primitive and apply the reliability defaults so the job doesn't **double-run**, **silently die**, or **corrupt state on retry**.

## When to use
- "run X every night / every 15 min / on the 1st", "add a scheduled cleanup/sync/report job"

## When NOT to use
- Triggered by an event (message, webhook, file arrival) → that's a consumer/function, not a cron
- A one-shot task → just run it
- An always-on worker → that's a Deployment/service

## Inputs
- `org-profile.yaml` → `platform` (picks the primitive) and `obs_backend` (alerting)
- The **schedule** (cron expression) and the **job command/image**
- `stack-interface.yaml` (if present) → deploy via the `stack-adapter` wrappers, not raw `kubectl`/`az`

## Steps
1. **Pick the primitive by `platform`** (refuse if unset/unsupported):
   - `aks` / `k8s` → Kubernetes **CronJob** (Helm template under the chart).
   - `webapp` / `serverless` → Azure **Functions timer trigger** (NCRONTAB) or **Container Apps job** (cron) — not k8s.
   - `vm` → **systemd timer** (preferred over crontab: logging, dependencies, accuracy).
   - `ecs` → EventBridge Scheduler → ECS task.
2. **Schedule** — validate the cron expression; **state the timezone explicitly** (k8s `spec.timeZone`; NCRONTAB `WEBSITE_TIME_ZONE`); never assume UTC silently. Document the next 3 run times.
3. **Reliability defaults (mandatory — this is the point):**
   - **No double-run**: k8s `concurrencyPolicy: Forbid` (or `Replace`); Functions singleton.
   - **Timeout**: `activeDeadlineSeconds` (k8s) / function timeout — a hung run must die.
   - **Retries with backoff**: `backoffLimit` + `restartPolicy: Never|OnFailure`; bounded, not infinite.
   - **Missed runs**: `startingDeadlineSeconds` so a controller outage doesn't fire a storm of catch-up runs.
   - **History**: `successfulJobsHistoryLimit` / `failedJobsHistoryLimit` so logs are inspectable but bounded.
   - **Idempotency**: the job MUST be safe to run twice (natural idempotency, a run-lock, or an idempotency key). State the strategy explicitly.
4. **Observability + alerting** (via `observability-gen` / `obs_backend`): structured logs with a run id; emit start/success/failure + duration metrics; **alert on failure AND on missed run** — a cron that stops running is the failure mode that goes unnoticed. Concrete missed-run detector per `obs_backend`:
   - **grafana/prometheus**: emit a `job_last_success_timestamp` gauge; alert `time() - job_last_success_timestamp{job="X"} > 2 * <interval_seconds>` (fires when a run is overdue, even if the scheduler is dead). For k8s also alert on `kube_job_status_failed > 0`.
   - **datadog**: a metric monitor on `job.last_success` age, or a Datadog **Check** with `no data` alerting.
   - **cloudwatch**: alarm on the custom `LastSuccess` metric with `treatMissingData: breaching`.
   - vendor-agnostic fallback: ping a **Healthchecks.io-style** dead-man URL on success; the service alerts when the ping doesn't arrive on schedule.
   - **`langfuse`/`honeycomb`**: LLM/event tracing, NOT an infra-metrics backend — do not wire cron missed-run alerts there. Use the vendor-agnostic fallback above (or the org's real metrics backend).
5. **Secrets**: pull from the secret store / mounted secret, never inline env literals.
6. **Deploy**: emit the manifest. If `stack-interface.yaml` exists, route through `stack-adapter` **only for ops it has a wrapper for**: Helm-templated CronJob → `deploy_cmd`; Functions timer → `func_deploy_cmd`; systemd timer → `vm_systemd_apply_cmd`. If the needed wrapper key is blank/absent, `stack-adapter` returns `MISSING-MAPPING` — do NOT stall: emit the manifest + the standard apply command directly (`kubectl apply` / `systemctl enable --now` / `func azure functionapp publish`) and note that no enterprise wrapper was declared for this op.

## Output / validation
- The scheduled-job manifest (CronJob/timer/systemd unit) + a short runbook: what it does, schedule + timezone, idempotency strategy, on-failure action, where its alert fires.
- Validation: cron expression parses; concurrency + timeout + backoff + history limits all set; failure alert wired; idempotency strategy stated.

## Refuses when
- `platform` unset or unsupported in `org-profile.yaml`.
- The job mutates state but no idempotency/locking strategy is given (refuse — a retried non-idempotent cron corrupts data).
- Schedule missing or the cron expression is invalid.
