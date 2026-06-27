# VERIFY — llm-gen

Run after `llm-gen` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] all four artifacts emitted: a TYPED provider wrapper (request/response types, error handling, retries), prompt management (versioned templates, var injection), a golden-set eval harness (fixtures + scoring), and per-call cost/token tracking
- [ ] output matches `org-profile.yaml` `llm_provider` (anthropic | openai | azure | bedrock | vertex), exactly ONE — the wrapper targets THAT provider. For `azure`: uses the Azure client (`azure_endpoint` + `api_version` + deployment name, NOT a bare model id), not the plain `openai` client
- [ ] no secrets in source: API keys/endpoints from ENV/config — `! grep -rEi '(api[_-]?key|endpoint)\s*[:=]\s*["'\''][^"'\'' $]+' <generated-dir>`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] the provider SDK installed (e.g. `anthropic`, `openai`) · a type checker (`command -v mypy`) → note absent, don't fail

## Functional
- The typed wrapper type-checks/compiles, the eval harness runs against the golden set and produces scores, and the token/cost counters populate on a sample call.
