---
name: knowledge-base
description: Use when governing a RAG knowledge base's CONTENT lifecycle — source ingestion + content-hash dedup, the chunk/metadata taxonomy retriever's filters consume, freshness/re-sync (TTL + eviction), citation policy. Triggers — "set up our knowledge base", "keep the KB fresh", "how do we cite sources", "stale content". NOT for the retrieval mechanism (chunking, embeddings, vector store, hybrid search, recall@k eval) — that is retriever; NOT for generation (llm-gen) or online scoring (online-llm-eval). Reads org-profile.yaml `llm_provider` + `vector_store`; refuses absent either.
---

# Knowledge Base — content governance on top of the retriever

This skill governs **what enters the corpus and how long it lives** — source ingestion, content-hash dedup, the chunk/metadata taxonomy, freshness/re-sync, and the citation policy. It is a taxonomy/policy layer that sits ON TOP of `retriever`'s mechanism; it does not implement the splitter, embeddings, store, or search, and it does not enforce anything — the deterministic teeth are the re-sync schedule (`cronjob` / CI) and the freshness SLI alert (`observability-gen`), never this skill.

## When to use
- "stand up our knowledge base / corpus", "ingest + dedup these document sources"
- "keep the KB fresh / re-sync changed sources", "this answer cited stale content"
- "what's our citation & attribution policy", "define the chunk metadata taxonomy"

## When NOT to use
- The chunking ALGORITHM, embeddings, vector store, hybrid search, reranking, recall@k/MRR eval → `retriever` (KB defines the taxonomy its filters consume; it does NOT reimplement the splitter)
- Answer generation / prompting over retrieved chunks → `llm-gen` (and context shaping → the `context-engineering` agent)
- Online answer-quality / RAGAS scoring of live traffic → `online-llm-eval`
- No `llm_provider` / `vector_store` declared → this skill refuses

## Inputs
- `org-profile.yaml` → `llm_provider` (anthropic | openai | azure | bedrock | vertex) — REQUIRED; the embeddings owner, applied via `retriever`, never re-wired here
- `org-profile.yaml` → `vector_store` (pgvector | azure-ai-search | qdrant | pinecone | …) — REQUIRED; the store this corpus governs. Refuse without both keys (no store to govern)
- The **source inventory**: each system/feed, its format, owner, and sensitivity/ACL
- The **freshness requirement** per source (how stale is acceptable) and the **citation/attribution format** the product must render
- `stack-interface.yaml` (optional) → for Azure-wrapped sources/stores, resolve endpoints/auth via `stack-adapter`; never hardcode an endpoint or key

## Steps
1. **Read `org-profile.yaml`** — resolve `llm_provider` and `vector_store`. If either is unset (or `none`), REFUSE: there is no store/embeddings owner to govern. Verify the store's metadata-filter capability against current docs (which fields are filterable/indexable changes per store).
2. **Ingestion + dedup** — one connector per source; compute a **content hash** (e.g. `sha256` of normalized bytes) per document and skip re-ingest when the hash is unchanged (idempotent — re-running an unchanged source is a no-op). Capture `source`, `owner`, `acl`, and `sensitivity` at ingest; quarantine PII/secrets OUT of the corpus (route detection to the `gitleaks` hook / a PII scrubber, not into the index).
3. **Chunk / metadata TAXONOMY** — define the metadata SCHEMA that `retriever`'s filters consume, every chunk carrying at minimum:
   - `source` (system/URI), `version`, `effective_date` (for freshness)
   - `acl` / `sensitivity` (drives pre-filtering by tenant/role)
   - `citation_id` (stable, for attribution)
   This is the taxonomy DECISION — the chunking algorithm itself stays in `retriever`.
4. **Freshness & re-sync** — set a per-source **TTL / max-age** from the stated staleness tolerance and a change-detection re-ingest cadence. Schedule the re-sync via the `cronjob` skill (do not hand-roll a scheduler). On re-sync: **evict or supersede** stale chunks by `source`+`version` so retrieval never returns dead content.
5. **Citation policy** — every chunk carries a stable `citation_id` + source URI; document the attribution FORMAT the product renders and an **allowlist of quotable sources** (what may be quoted verbatim vs paraphrased only). Unquotable/unlicensed sources are excluded from the corpus.
6. **Defer to `retriever`** — hand chunking / embeddings / indexing to `retriever` (it owns the splitter, the embeddings client for `llm_provider`, the store adapter for `vector_store`). KB writes NO splitter and NO embeddings code — it governs entry and lifetime only.
7. **Freshness SLI** — define the SLI as **max age of any served chunk** against its source TTL, and wire its alert via `observability-gen` so staleness pages instead of silently rotting.

## Output / validation
- An ingestion + dedup policy (content-hash, ACL/sensitivity capture, PII quarantine), the chunk **metadata taxonomy** `retriever`'s filters consume, a per-source freshness/TTL + re-sync cadence with stale-chunk eviction, and a citation/attribution policy + quotable-source allowlist — all driven by `org-profile.yaml` `llm_provider` + `vector_store`.
- Validate: ingest a sample source, mutate it, re-sync, and confirm only changed chunks re-embed and the stale version is no longer retrievable; confirm every chunk carries `source` + `effective_date` + `citation_id` + `acl`.
- Boundary: this skill decides policy and taxonomy; the deterministic gate is the `cronjob` re-sync + the `observability-gen` freshness alert — KB advises, infra enforces.

## Refuses when
- `llm_provider` or `vector_store` is unset / `none` in `org-profile.yaml` (no embeddings owner or store to govern).
- Asked to implement the chunking algorithm, embeddings, vector store, hybrid search, or the recall@k/MRR eval — that is `retriever`; KB defines the taxonomy, not the mechanism.
- Asked to generate answers or score answer quality — route to `llm-gen` / `online-llm-eval`.
- Asked to ingest a source with no defined `acl`/`sensitivity`, or to add content with no `citation_id` / not on the quotable-source allowlist.
