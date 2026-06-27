# VERIFY — online-llm-eval

Run after `online-llm-eval` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] Langfuse LLM-as-a-judge config exists: versioned judge prompts emitting STRUCTURED scores + reasoning (not a free-text grade): `grep -rEqi 'langfuse|llm-as-a-judge' . && grep -rEqi 'score|reasoning' . && echo OK || echo MISSING`
- [ ] online evaluators score live traces (sampling rate + trace selection) AND dashboards/alerts fire on score regression: `grep -rEqi 'evaluator|sampling' . && grep -rEqi 'regression|drift|alert|dashboard' . && echo OK || echo MISSING`
- [ ] RAG present → RAGAS-style metrics (faithfulness/answer-relevance/context-precision) over retriever output: `grep -rEqi 'faithfulness|answer.relevance|context.precision|ragas' . && echo OK || echo CHECK`
- [ ] (profile-driven) judge runs under the `llm_provider` from `org-profile.yaml` (azure = Azure OpenAI) and evaluators target `obs_backend` (`langfuse`)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v langfuse` · `python -c 'import langfuse'` → note absent, don't fail

## Functional
- Judge prompts return parseable structured scores on a sample trace, evaluators populate scores on live traces, and a seeded score regression fires the alert (observe-only — it does not gate traffic).
