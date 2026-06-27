---
name: llm-gen
description: Use when you need a typed LLM client wrapper for the org's DECLARED provider (anthropic/openai/azure/bedrock/vertex) plus prompt management, a golden-set eval harness, and cost/token tracking. NOT for non-LLM app code. Reads org-profile.yaml llm_provider (one per profile) and refuses without it.
---

# LLM Generator

## When to use
- "scaffold the LLM client/wrapper" for the provider declared in the profile
- You need prompt management, a golden-set eval harness, and cost/token tracking wired in

## When NOT to use
- Non-LLM application logic → use the relevant app/framework generator
- Auth/observability/infra → use `auth-gen` / `observability-gen` / `iac-gen`
- Scoring PRODUCTION traffic (online evals) → use `online-llm-eval`; this skill owns the OFFLINE golden-set harness only
- No declared provider → this skill refuses

## Inputs
- `org-profile.yaml` → `llm_provider` (anthropic | openai | azure | bedrock | vertex) — REQUIRED, exactly one per profile

## Steps
1. Read `org-profile.yaml`; resolve `llm_provider`. If unset, REFUSE.
2. Verify the provider's SDK against current official docs BEFORE generating (SDKs change fast — model IDs, params, client init).
   - **`azure` = Azure OpenAI Service** — distinct from `openai`: use the Azure client (`AzureOpenAI` / `azure_endpoint` + `api_version` + **deployment name** instead of a model id), auth via API key or AAD/managed-identity. If the org also declares `stack-interface.yaml`, get the endpoint/auth wrapper from `stack-adapter`. Never hardcode endpoint/key.
3. Generate a TYPED wrapper around the provider client (request/response types, error handling, retries).
4. Generate prompt management (versioned templates, variable injection, separation from code).
5. Generate a golden-set eval harness (fixtures + scoring) and cost/token tracking (per-call token + cost accounting via ENV-configured keys).

## Output / validation
- Typed provider wrapper + prompt management + golden-set eval harness + cost/token tracking
- Verify types compile, the eval harness runs against the golden set, and token/cost counters populate
- API keys/endpoints come from ENV/config, never literal in source

## Refuses when
- `llm_provider` is unset in `org-profile.yaml`
- More than one provider is requested for a single profile (one provider per profile)
- The provider is not one of anthropic/openai/azure/bedrock/vertex
