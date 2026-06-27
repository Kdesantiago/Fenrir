---
name: langgraph-workflow
description: Use when scaffolding a LangGraph workflow/agent graph — typed State, nodes as pure functions, conditional routing, a checkpointer for persistence, human-in-the-loop interrupts, streaming, and per-node retries. This is LLM-app product code, NOT couche-0 delivery infra. NOT for non-LLM control flow, NOT for a single-call wrapper (use llm-gen). Reads org-profile.yaml llm_provider for the model client and refuses without it.
---

# LangGraph Workflow

Product-building, not delivery: this scaffolds application code for an LLM workflow. It does not gate or enforce anything (that's couche-0 / `repo-bootstrap`).

## When to use
- "scaffold a LangGraph graph/agent", "wire a multi-step LLM workflow with persistence + human-in-the-loop"
- You need a stateful graph: routing between nodes, checkpoints, interrupts, streaming, retries

## When NOT to use
- Plain (non-LLM) control flow / a state machine that calls no model → use ordinary app code
- A single model call or a thin typed client → `llm-gen`
- Prompt/context shaping (what goes in the window, ordering, few-shot) → `context-engineering` agent
- Retrieval infra (chunking, embeddings, vector store) → `retriever`
- No declared `llm_provider` → this skill refuses

## Inputs
- `org-profile.yaml` → `llm_provider` (anthropic | openai | azure | bedrock | vertex) — REQUIRED, selects the chat-model client
- `stack-interface.yaml` (optional) → for `azure`, get the endpoint/auth wrapper from `stack-adapter`; never hardcode endpoint/key

## Steps
1. Read `org-profile.yaml`; resolve `llm_provider`. If unset or `none`, REFUSE.
2. Resolve the chat-model client for the provider — verify exact class/init against current LangGraph + LangChain docs (they move fast):
   - `anthropic` → `ChatAnthropic`
   - `openai` → `ChatOpenAI`
   - `azure` (Azure OpenAI Service) → `AzureChatOpenAI` (`azure_endpoint` + `api_version` + **deployment name**, not a model id; AAD/managed-identity or key)
   - `bedrock` → `ChatBedrock`/`ChatBedrockConverse`; `vertex` → `ChatVertexAI`
   - Keys/endpoints from ENV/config only.
3. Define a typed **State** — `TypedDict` (or Pydantic model) with reducers for accumulating channels (e.g. `messages` via `add_messages`).
4. Write **nodes as pure functions** `state -> partial-state-update`; no hidden globals, side effects isolated and injected.
5. Build the graph: `StateGraph(State)`, add nodes, **conditional edges** for routing (a router fn returning the next node key), entry/finish points.
6. Add a **checkpointer** for persistence (memory in dev; a durable saver — sqlite/postgres — in prod), keyed by `thread_id`.
7. Add **human-in-the-loop interrupts** (interrupt at a node; resume by updating state + re-invoking with the same thread).
8. Wire **streaming** (token/state stream) and **per-node error handling + retries** (bounded retry with backoff; a fallback/error node so one bad node doesn't kill the run).

## Output / validation
- A typed-`State` graph module: pure-function nodes, conditional routing, checkpointer, interrupt points, streaming, per-node retries — provider client from the profile, secrets from ENV
- Validate: the graph compiles, a happy-path run streams to completion, an interrupt pauses and resumes on the same `thread_id`, a forced node failure hits the retry/error path
- Wrap model calls so cost/token tracking flows through `llm-gen`'s accounting and (if `obs_backend: langfuse`) traces via `observability-gen`

## Refuses when
- `llm_provider` is unset or `none` in `org-profile.yaml`
- The task is non-LLM control flow, or a single-call wrapper that doesn't need a graph (route to `llm-gen`)
