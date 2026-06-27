# VERIFY — langgraph-workflow

Run after `langgraph-workflow` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the graph module has ALL required parts: a typed `State` (`TypedDict`/Pydantic with reducers, e.g. `messages` via `add_messages`), nodes as pure `state -> partial-update` functions, conditional edges (router fn), a checkpointer, interrupt point(s), streaming, and per-node bounded retries + an error/fallback node
- [ ] chat-model client matches `org-profile.yaml` `llm_provider`: anthropic→`ChatAnthropic`, openai→`ChatOpenAI`, azure→`AzureChatOpenAI` (`azure_endpoint`+`api_version`+deployment name, not a model id), bedrock→`ChatBedrock*`, vertex→`ChatVertexAI` — and NOT a wrong-provider client
- [ ] no secrets in source: keys/endpoints from ENV/config — `! grep -rEi '(api[_-]?key|azure_endpoint)\s*[:=]\s*["'\''][^"'\'' $]+' <generated-dir>`
- [ ] model calls are wrapped so cost/token tracking flows through `llm-gen` (not re-implemented here)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `python3 -c 'import langgraph'` · `python3 -c 'import langchain'` · the provider SDK · a durable checkpointer backend (sqlite/postgres) → note absent, don't fail

## Functional
- The graph compiles; a happy-path run streams to completion; an interrupt pauses and resumes on the SAME `thread_id` from the checkpointer; a forced node failure hits the retry/error path instead of killing the run.
