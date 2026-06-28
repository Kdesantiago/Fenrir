# VERIFY — knowledge-base

Run after `knowledge-base` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] profile keys resolved: `llm_provider` AND `vector_store` are set in `org-profile.yaml` (else the skill should have REFUSED) — `grep -Eq '^llm_provider:' org-profile.yaml && grep -Eq '^vector_store:' org-profile.yaml && echo OK || echo MISSING`
- [ ] every ingested chunk carries the taxonomy metadata `retriever`'s filters consume: `source`, `effective_date`, `citation_id`, and `acl`/`sensitivity` — a sampled chunk's metadata has all four, none null
- [ ] content-hash dedup exists and is idempotent: re-ingesting an UNCHANGED source is a no-op (no new chunks, no re-embed) — the ingestion path records a per-document hash and skips on match
- [ ] a per-source freshness cadence (TTL / max-age) is defined AND stale chunks are evicted/superseded on re-sync (no dead content retrievable); the schedule defers to the `cronjob` skill, not a hand-rolled scheduler
- [ ] a citation/attribution policy + quotable-source allowlist is documented, and every chunk has a stable `citation_id` + source URI
- [ ] KB defers chunking/embeddings/indexing to `retriever` — no reimplemented splitter or embeddings client lives in the KB output (`! grep -rEi '(text_?splitter|chunk_?text|embed(dings)?_client|\.encode\(|RecursiveCharacter)' <kb-generated-dir> && echo OK || echo "LEAK: reimplemented retriever infra"`)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v sha256sum` (or an equivalent hashing tool for the dedup step) → note absent, don't fail
- [ ] the `cronjob` skill is available for the re-sync schedule and the `vector_store` SDK is installed → note absent, don't fail
- [ ] a PII/secret scrubber or the `gitleaks` hook is present to quarantine sensitive content at ingest → note absent, don't fail

## Functional
- Ingest a sample source, then mutate it and re-sync: confirm only the CHANGED chunks re-embed (unchanged ones are content-hash no-ops) and the stale prior version is no longer retrievable from the `vector_store`. Confirm a retrieval honors an `acl` pre-filter and that returned chunks resolve to a valid `citation_id` + source URI per the citation policy. The freshness SLI (max age of any served chunk) reconciles with the per-source TTL.
