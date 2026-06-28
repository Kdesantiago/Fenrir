# Spec — Tech-lead & AI-architect workflow completion (epic-9)

## Problem
Fenrir delivers code well, but for a **tech-lead + AI-architect** three things are missing: (a) the pack is not **self-documenting** — no single place shows what every agent/hook/skill does or lets you watch the orchestration run; (b) the **AI-architect lifecycle** lacks a design-time threat model and a debt/drift view; (c) the workflow still has **manual chores** (compaction config, branch→plan) and no single autonomous chain. Full autonomy is explicitly *out* — the human merge gate stays.

## Users & success metric
- **User:** a solo tech-lead/AI-architect operating Fenrir across repos.
- **Success:** a newcomer understands the pack from the dashboard alone (no code reading); a prompt/architecture change is risk-assessed before code; debt is tracked, not lost; the only manual step left is the human merge.

## Scope (the epic) — decomposed onto the board as epic-9
1. **F-A — Dashboard "Agents & workflow" view** *(v1 cut — build first)*: a **catalog** of every agent + hook + skill with its description (read from frontmatter/docstrings) and, for hooks, *when it fires*; plus a **live orchestration** section — recent/running subagent runs (which agent, what it did, cost), auto-refreshing, showing the delivery pipeline. Directly the onboarding + "see agents execute" asks.
2. **F-B — AI threat-model skill** (`ai-threat-model`): design-time LLM-system threat modeling (prompt-injection, data-exfil, tool-abuse, jailbreak, excessive-agency) → writes findings; design-time counterpart to the runtime `security-guardrail`.
3. **F-C — Tech-debt / architecture-drift tracker** (`tech-debt`): catalog debt + detect drift vs the DAT/ADRs, file items onto the board.
4. **F-D — Safe automation glue**: document + enable **auto-compaction at a token threshold** (the "compaction" ask — a Claude Code client setting + our focus hook), and a **branch-create → auto-plan** hook.
5. **F-E — Meta-orchestrator command** (`/fenrir:auto`): chain plan→deliver→ship with per-stage checkpoints, **stops on any gate failure**, never auto-merges (the human gate is the terminal step).
6. **Small fixes** (fold into F-A's PR): audit the 5 stray non-`fenrir:` command refs; document the auto-compaction trigger.

## v1 cut (build now)
**F-A + the small fixes.** It is the highest-value, lowest-risk, directly-requested slice and gives the onboarding surface the rest of the epic will document. F-B/C/D/E are planned on the board and delivered next, each its own gated PR.

## Acceptance criteria (F-A)
- `GET /api/catalog` returns every agent, hook, and skill with `{name, kind, description, …}` read from disk (frontmatter / docstring); hooks include the event they fire on.
- A dashboard view lists them grouped by kind, searchable, each with its description — readable with zero code access.
- The live section shows recent subagent runs (agent type, what it did, when, cost) and auto-refreshes.
- Command-prefix audit: every command cross-reference uses `fenrir:` (or is confirmed a false positive).
- A short doc explains enabling auto-compaction at a threshold (why our hook only *focuses*, not *triggers*).

## Out of scope
- Auto-merge / removing the human gate (deliberately).
- Real-time streaming of in-flight token deltas (poll/refresh is enough for v1).
- Rebuilding existing capabilities (llm-gen eval harness, online-llm-eval, observability, etc.).

## Profile keys
`platform`/`framework` unchanged (this is plugin + dashboard work on the Fenrir repo itself).

## Risks / riskiest assumption
- **Riskiest:** the catalog reads plugin files from disk — path resolution from the dashboard process to the plugin root must be robust (repo root = `Path(__file__).parents[2]`), and degrade gracefully when run outside the repo.
- "Live" via polling telemetry is honest but not truly real-time — acceptable for v1; flagged.
- Meta-orchestrator (F-E) is the riskiest *feature* — careful stop conditions; deferred out of v1.

## Decisions
- Full autonomy rejected; automate chores, not judgment.
- AI-eval CI gate (offered) NOT selected — deferred.
- Build F-A first; plan B–E on the board.
