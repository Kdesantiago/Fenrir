# VERIFY — llm-cost-monitor

Run after `llm-cost-monitor` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] all four monitoring artifacts emitted: cost-attribution tags (every call tagged with `route` + `model`, optionally team/tenant), budget thresholds + alert config (soft/hard, from config), dashboards (cost over time / by model / by route / top spenders), and spend-anomaly rules (rolling-baseline deviation)
- [ ] price book + cost sink match `org-profile.yaml`: `llm_provider` sets the per-model price book (azure = Azure OpenAI deployment pricing) and metrics/traces export via the declared `obs_backend` (`langfuse` cost views, else the declared backend) — endpoint/keys from ENV, never hardcoded (`! grep -rEi '(api[_-]?key|host|endpoint)\s*[:=]\s*["'\''][^"'\'' $]+' <generated-dir>`)
- [ ] it CONSUMES `llm-gen`'s per-call token/cost counters as source of truth and does NOT re-implement token counting or pricing math (no duplicate metering); it does not claim to be a hard budget cap

## Informational (tooling presence — does NOT block; note if absent)
- [ ] the `obs_backend` SDK/CLI (langfuse / grafana / datadog / cloudwatch client) → note absent, don't fail

## Functional
- A sample run shows cost attributed per route+model; a forced over-budget run fires the alert; an injected token-spike trips the anomaly rule. Switching `obs_backend` is ENV/config-only (backend name not baked into source).
