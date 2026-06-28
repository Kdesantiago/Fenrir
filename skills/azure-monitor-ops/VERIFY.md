# VERIFY — azure-monitor-ops

Run after `azure-monitor-ops` has been applied (a live KQL triage against an Azure workspace). All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the output prints the EXACT KQL executed for every query (so the triage is reproducible) — not just prose results: `grep -Eqi 'where TimeGenerated|summarize|AppExceptions|AppRequests|AzureActivity|\| project' triage.md && echo OK || echo MISSING`
- [ ] every cited number/error signature came from a REAL az MCP result (`mcp__azure__monitor` / `mcp__azure__kusto`), tied to a named workspace + time window — no invented rows, no from-memory error messages: `grep -Eqi 'workspace|TimeGenerated|ago\(' triage.md && echo OK || echo MISSING`
- [ ] cross-refs `observability-gen` as the sibling that DEFINES the signals + EMITS the OTel/SLO/alert code (generate side) while this skill only QUERIES (operate side) — and does not generate init code: `grep -q 'observability-gen' triage.md && echo OK || echo MISSING`
- [ ] read-only boundary stated: the report asserts it created no alerts, changed no config, and remediated nothing, and names `azure-sre` (applens/sreagent) as the owner of root-cause + remediation orchestration: `grep -Eqi 'read-only|no (alert|config|mutation)|created nothing' triage.md && grep -q 'azure-sre' triage.md && echo OK || echo MISSING`
- [ ] refuses (no fabricated results) when `obs_backend` is not `azure-monitor`, when no live workspace is reachable via the az MCP, or when `stack-interface.yaml` is present and `stack-adapter` returns `MISSING-MAPPING`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` — note absent, don't fail (the skill drives the az MCP, not the local CLI, but its presence helps spot-check a query in the portal)
- [ ] az MCP reachable: a `mcp__azure__applicationinsights` / `mcp__azure__monitor` call resolves at least one App Insights component + a Log Analytics workspace — note if unreachable (then the skill should have refused)
- [ ] `command -v jq` — for spot-checking exported query JSON; note absent, don't fail

## Functional
Run the skill against a live (or sandbox) Azure workspace whose `obs_backend` is `azure-monitor`. Take the triage summary's TOP query, copy the printed KQL verbatim into the Azure portal (Log Analytics / ADX) against the same workspace and time window, and confirm it returns the same result shape (same top error signatures / latency profile) — proving the run was real and reproducible, not invented. Confirm the run mutated nothing (no alert rule, diagnostic setting, or threshold was created) and that, with `obs_backend != azure-monitor` or no workspace reachable, the skill refuses rather than fabricating rows.
