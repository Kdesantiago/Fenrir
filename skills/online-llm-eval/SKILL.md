---
name: online-llm-eval
description: Use when you need ONLINE (production-traffic) LLM evaluation — Langfuse LLM-as-a-judge judge prompts producing structured scores + reasoning, online evaluators scoring real-time traces, dashboards/alerting on score regressions, and RAGAS-style retrieval metrics for RAG apps. Complements the OFFLINE golden-set evals from llm-gen (cross-ref, do not reimplement). NOT the offline harness (llm-gen) nor cost tracking (llm-cost-monitor). Reads org-profile.yaml `llm_provider` + `obs_backend` (langfuse ideal) and refuses without `llm_provider`.
---

# Online LLM Eval

## When to use
- "score production traffic", "LLM-as-a-judge on live traces", "alert when quality regresses"
- "RAG eval on real queries" (faithfulness/answer-relevance/context-precision)
- You already have offline golden-set evals and need the online half

## When NOT to use
- The offline golden-set eval harness → that is `llm-gen` (cross-ref; do not duplicate)
- LLM cost/spend monitoring → use `llm-cost-monitor`
- Scaffolding the retriever itself → use `retriever` (this scores its output online)
- No declared `llm_provider` → this skill refuses

## Inputs
- `org-profile.yaml` → `llm_provider` (REQUIRED — judge model; `azure` = Azure OpenAI Service) and `obs_backend` (`langfuse` is ideal — it is the trace + evaluator backend)
- Existing production traces in `obs_backend`; the offline eval set from `llm-gen` (for parity, not re-run here)

## Steps
1. Read `org-profile.yaml`; resolve `llm_provider` (REFUSE if unset) and `obs_backend`. If `obs_backend` is not `langfuse`, note the degraded path (native online evaluators are Langfuse-specific).
2. Author judge prompts (Langfuse LLM-as-a-judge): versioned prompts emitting **structured scores + reasoning**, run by the configured `llm_provider` (works with Azure OpenAI).
3. Wire online evaluators that score real-time production traces as they arrive (sampling rate + which traces).
4. Add dashboards + alerting on **score regressions** (drift/drop on a judged dimension), routed through `obs_backend`.
5. For RAG apps, add RAGAS-style retrieval metrics (faithfulness, answer-relevance, context-precision/recall) over `retriever` output.
6. Triggering: as a Langfuse online evaluator (primary, on production traces) and/or via the plugin's opt-in `prompt`-type LLM-as-judge hook on `Stop` (see `templates/optional-hooks.json`) — the hook **wiring lives in the plugin's hooks**, not in this skill.

## Output / validation
- Judge prompts + online evaluators + regression dashboards/alerts + (for RAG) RAGAS-style metrics, all on `obs_backend`
- Verify judge prompts return parseable structured scores, evaluators populate scores on live traces, and a seeded regression fires the alert
- Online eval observes and reports quality; it does not gate or block traffic

## Refuses when
- `org-profile.yaml` is missing, or `llm_provider` is unset
- Asked to build the OFFLINE golden-set harness (route to `llm-gen`) or cost tracking (route to `llm-cost-monitor`)
- `obs_backend` provides no LLM-trace/evaluator surface and no alternative is acceptable (native online evaluators assume `langfuse`)

## Sources
- https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge
- https://langfuse.com/docs/evaluation/overview
