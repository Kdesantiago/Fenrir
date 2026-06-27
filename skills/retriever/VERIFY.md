# VERIFY — retriever

Run after `retriever` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] ALL retrieval parts emitted: a configurable chunker (size/overlap + structure-aware, source offsets kept for citation), an embeddings client, a vector-store adapter (`upsert`/`query`/`delete`), hybrid search (BM25 + dense) with fusion (RRF) + rerank, metadata filtering, and a recall@k/MRR eval against a golden set
- [ ] embeddings provider matches `org-profile.yaml` `llm_provider` (azure → Azure OpenAI embeddings deployment, etc.); the embedding model + dimension are recorded so the index matches; for `none`/unset the skill should have REFUSED
- [ ] vector store comes from `org-profile.yaml` `vector_store` (or was explicitly asked for) and lives behind the one adapter seam — swapping stores is adapter/config-only, no scattered store calls
- [ ] no secrets in source: store/embeddings endpoints + keys from ENV/config — `! grep -rEi '(api[_-]?key|endpoint)\s*[:=]\s*["'\''][^"'\'' $]+' <generated-dir>`

## Informational (tooling presence — does NOT block; note if absent)
- [ ] the embeddings SDK · the store's client/driver (pgvector/qdrant/azure-ai-search) · a BM25/lexical lib · a reranker → note absent, don't fail

## Functional
- Ingest a sample corpus, run the eval: `recall@k` and `MRR` meet the configured target (and the eval FAILS below it). Swapping the store touches only the adapter/config.
