---
name: azure-monitor-ops
description: Use when triaging a running Azure service by querying LIVE telemetry via the az MCP — run KQL over Azure Monitor / App Insights / Log Analytics (and ADX via Kusto), pull metrics + activity logs, return a triage summary printing the exact KQL run. Triggers — "query our logs", "run this KQL", "why is prod erroring", "check App Insights". NOT for OTel/SLO/alert code (observability-gen), NOT for root-cause/remediation (azure-sre), NOT for error-budget policy (error-budget). Read-only/advisory, not a gate. Reads org-profile.yaml `obs_backend` (azure-monitor) + `platform`.
---

# Azure Monitor Ops — live KQL triage

Triage a running Azure service by reading **real** telemetry through the **az MCP**: run KQL over Azure Monitor / Application Insights / Log Analytics (and ADX via Kusto), pull metrics and the activity log, and hand back a reproducible triage summary. This skill **operates a LIVE workspace** but is strictly **read-only and advisory** — it QUERIES and PROPOSES a triage, it never creates alerts, changes config, or remediates. Every row in the output comes from an actual `mcp__azure__monitor` / `mcp__azure__kusto` result; nothing is invented from memory, and the **exact KQL executed is always printed** so a human can re-run it. The deterministic side lives elsewhere: `observability-gen` defines the signals and emits the code, and the gate that stops a bad deploy is the CI/branch-protection pipeline + alert rules — not this skill.

## When to use
- "query our logs", "run this KQL", "why is the service erroring in prod", "check App Insights", "triage from Log Analytics", "what does the activity log show"
- You are triaging a running Azure service and need to READ live telemetry / metrics / logs / activity events to find the failing signal
- A runbook step (from `incident-runbook`) says "pull the error signature from Log Analytics" — this skill is that live-query arm

## When NOT to use
- Generating OTel SDK init, semantic conventions, or the SLI/SLO + alert-rule *definitions* → `observability-gen` (it EMITS code on the generate side of the generate-vs-operate axis; this skill only QUERIES live data, it never instruments)
- Orchestrating end-to-end incident root-cause + remediation → `azure-sre` (that agent drives `mcp__azure__applens` / `mcp__azure__sreagent` and calls THIS query style as one input; this skill does the live KQL pull, not the orchestration or any fix)
- Defining the error-budget burn policy / its delivery gate → `error-budget`
- Writing the incident plan / recovery playbook → `incident-runbook` (this skill is the live-query arm a runbook step invokes, not the plan)
- `obs_backend` is not `azure-monitor`, or no live workspace is reachable → refuse (do not fabricate query results)

## Inputs
- **az MCP (live read-only)** — the triage is built entirely from these tools:
  - `mcp__azure__monitor` → run KQL over the Log Analytics workspace + resource logs, pull metrics, and read the activity log
  - `mcp__azure__applicationinsights` → list the App Insights component(s) backing the service and resolve which workspace its telemetry lands in
  - `mcp__azure__kusto` → run KQL against Azure Data Explorer (ADX) when telemetry lands in a Kusto cluster rather than (or in addition to) Log Analytics
- `org-profile.yaml` → `obs_backend` — REQUIRED, must be `azure-monitor` for this native path (any other value = wrong backend, refuse and route to the matching ops skill)
- `org-profile.yaml` → `platform` — scopes which resource types / tables to focus the triage on (aks → container/pod logs; webapp → App Service logs + App Insights requests; serverless → Functions traces)
- `stack-interface.yaml` (OPTIONAL) → when present, resolve workspace / login / subscription context through the `stack-adapter` agent; never emit raw `az login` / `az account set`

## Steps
1. **Confirm a live workspace is reachable — never hallucinate results.** Read `org-profile.yaml`; if `obs_backend` is not `azure-monitor`, REFUSE and name the matching backend's ops path. Resolve the App Insights component(s) with `mcp__azure__applicationinsights` and confirm the backing Log Analytics workspace (or ADX cluster) answers. If nothing resolves (az MCP not connected / no auth / no workspace), REFUSE — do not invent rows. If `stack-interface.yaml` exists, get the login/workspace context from `stack-adapter` first (embed verbatim; on `MISSING-MAPPING`, stop).
2. **Identify the workspace + tables.** List the available tables for the workspace via `mcp__azure__monitor` (e.g. `AppRequests`, `AppExceptions`, `AppTraces`, `ContainerLogV2`, `AzureActivity`) and pick the ones relevant to the triage question (errors, latency, saturation, recent deploys). Scope by `org-profile.yaml` `platform`.
3. **Compose the KQL for the triage question.** Write explicit, time-bounded KQL (always `| where TimeGenerated > ago(<window>)`) for the symptom: top error signatures (`AppExceptions | summarize count() by problemId, outerMessage`), latency (`AppRequests | summarize percentiles(DurationMs, 50, 95, 99)`), failure rate, or saturation. Keep each query small and named so it is reproducible.
4. **Run the KQL via the az MCP.** Execute against Log Analytics with `mcp__azure__monitor` (and `mcp__azure__kusto` when the telemetry is in ADX). Pull correlating **metrics** (`mcp__azure__monitor` metrics) and the **activity log** (`AzureActivity` / activity-log query) so a spike can be time-correlated to a deploy, scale event, or config change. Capture the real result set — no estimation.
5. **Return the result set + a reproducible triage summary.** Emit the top error signatures with counts, the latency/saturation profile, and the time correlation to deploys/changes — and ALWAYS print **the exact KQL executed** (and the workspace id / time window) for each query so the run is reproducible in the portal. Use the Output contract below.
6. **State the boundary, loudly.** Close by asserting: this is read-only triage — it READS the signals `observability-gen` defined and that a runbook step can invoke; it created no alerts, changed no config, and remediated nothing. Root-cause + remediation orchestration is `azure-sre` (applens/sreagent); the deterministic gate is the CI/branch-protection pipeline + the alert rules, not this skill. List exactly which az MCP read tools were used.

## Output / validation
- A triage summary with: top error signatures (signature + count + sample message), a latency/saturation profile, the activity-log/deploy correlation, AND **the exact KQL executed** for every query, plus the workspace id and time window — sourced entirely from `mcp__azure__monitor` / `mcp__azure__kusto`, no invented rows.
- Validate: re-running the printed KQL in the Azure portal (Log Analytics / ADX) against the same workspace + window yields the same result shape; every cited count came from a real az MCP call. No placeholder numbers, no from-memory error messages.
- Boundary reiterated: this skill **queries**, it does not generate or enforce. `observability-gen` emits the OTel init + SLO/alert definitions (generate side); `azure-sre` orchestrates root-cause + remediation; the deterministic gate is the pipeline + alert rules. This skill blocks and changes nothing.

## Refuses when
- `obs_backend` in `org-profile.yaml` is not `azure-monitor` (wrong backend for the native KQL path) — refuse and route to the matching backend's ops path.
- No live workspace is reachable via the az MCP (`mcp__azure__applicationinsights` / `mcp__azure__monitor` not connected / unauthenticated / no workspace) — refuse rather than fabricate query results, error signatures, or counts.
- `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING` for the login/workspace op — stop; do not fall back to a raw `az` command.
- Asked to MUTATE anything (create an alert rule, change a diagnostic setting, set a metric threshold, remediate) — out of scope; this skill is read-only. Route alert/SLO *definition* to `observability-gen` and remediation orchestration to `azure-sre`.
- Asked to GENERATE OTel init / SLI-SLO / alert code (`observability-gen`), define error-budget burn policy (`error-budget`), or be presented as a hard gate that blocks merges — route to the named sibling; this skill only queries and advises.
