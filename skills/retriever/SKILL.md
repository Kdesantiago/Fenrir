---
name: retriever
description: Use when scaffolding a RAG retriever — chunking strategy, embeddings via the declared provider, a vector-store adapter, hybrid (BM25 + dense) search with reranking, metadata filtering, and a retrieval-quality eval (recall@k / MRR against a golden set). This is LLM-app product code, NOT couche-0 delivery infra. NOT for generation/prompting (llm-gen / context-engineering). Reads org-profile.yaml llm_provider (embeddings) + a vector_store choice and refuses without an embeddings provider.
---

# Retriever (RAG)

Product-building, not delivery: this scaffolds the retrieval half of a RAG app. It does not gate or enforce anything (that's couche-0 / `repo-bootstrap`).

## When to use
- "scaffold a RAG retriever / vector search", "wire chunking + embeddings + hybrid search + reranking"
- You need metadata-filtered retrieval plus a retrieval-quality eval

## When NOT to use
- Generation, prompting, the model wrapper, prompt/eval harness → `llm-gen`
- Shaping what goes in the context window (injection order, compression, few-shot) → `context-engineering` agent
- The orchestration graph that consumes retrieval → `langgraph-workflow`
- No embeddings provider declared → this skill refuses

## Inputs
- `org-profile.yaml` → `llm_provider` (anthropic | openai | azure | bedrock | vertex) — REQUIRED, selects the **embeddings** client
- A vector-store choice — if not declared, ASK; suggest adding a `vector_store` key to `org-profile.yaml` (e.g. `pgvector | azure-ai-search | qdrant | pinecone`) so this is profile-driven, not guessed
- `stack-interface.yaml` (optional) → for Azure-wrapped stores/endpoints, resolve via `stack-adapter`; never hardcode endpoint/key

## Steps
1. Read `org-profile.yaml`; resolve `llm_provider` for embeddings. If unset or `none`, REFUSE.
2. Resolve the **vector store**: read `vector_store` if present; else ask and recommend declaring it. Verify the embeddings client and the store's SDK/index API against current docs before generating (provider/store APIs and embedding dims change).
3. **Chunking strategy** — pick by document type: token/char size + overlap, and structure-aware splitting (by heading/section/code block) where the corpus has structure. Make size/overlap configurable; keep source offsets for citation.
4. **Embeddings** via the declared provider (azure → Azure OpenAI embeddings deployment; etc.). Keys/endpoints from ENV/config; record the model + dimension so the index matches.
5. **Vector-store adapter** — a thin interface (`upsert`, `query`, `delete`) over the org's store (pgvector / Azure AI Search / …), so the store is swappable behind one seam.
6. **Hybrid search** — combine BM25/keyword (lexical) with dense vector search; fuse (e.g. RRF) and **rerank** the merged set (cross-encoder or the store's reranker).
7. **Metadata filtering** — structured pre/post filters (source, date, tenant, ACL) pushed into the store query where supported.
8. **Retrieval-quality eval** — score against a **golden set** (query → relevant-doc ids) with `recall@k` and `MRR`; pairs with `llm-gen`'s eval harness (retrieval eval feeds the end-to-end answer eval). Fail the eval below the configured target.

## Output / validation
- Chunker + embeddings client + store adapter + hybrid-search-with-rerank + metadata filtering + a recall@k/MRR eval against a golden set — provider/store from the profile, secrets from ENV
- Validate: ingest a sample corpus, run the eval, confirm recall@k/MRR meet the target; swapping the store requires only adapter/config changes
- Retrieval output is meant to be consumed by `context-engineering` (ordering/compression into the window) and the generation layer (`llm-gen`) — this skill stops at "good candidates", it does not generate answers

## Refuses when
- `llm_provider` is unset or `none` (no embeddings provider) in `org-profile.yaml`
- The task is generation/prompting rather than retrieval (route to `llm-gen` / `context-engineering`)
