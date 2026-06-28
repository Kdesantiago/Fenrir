# VERIFY — knowledge-base

Run after `knowledge-base` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] profile keys resolved: `llm_provider` AND `vector_store` are set in `org-profile.yaml` (else the skill should have REFUSED) — `grep -Eq '^llm_provider:' org-profile.yaml && grep -Eq '^vector_store:' org-profile.yaml && echo OK || echo MISSING`
- [ ] every ingested chunk carries the taxonomy metadata `retriever`'s filters consume — `source`, `effective_date`, `citation_id`, and `acl`/`sensitivity`, none null: query a sampled chunk and assert all four are present, e.g. `python -c "import json,sys; m=json.load(open(sys.argv[1])); req=['source','effective_date','citation_id','acl']; missing=[k for k in req if not m.get(k)]; print('OK' if not missing else 'MISSING:'+','.join(missing))" <sampled-chunk-metadata.json>`
- [ ] content-hash dedup is idempotent — re-ingesting an UNCHANGED source is a no-op (no new chunks, no embed calls): ingest the same source twice and assert the chunk-count delta is 0, e.g. `n1=$(kb-count-chunks <source>); kb-ingest <source>; n2=$(kb-count-chunks <source>); [ "$n1" = "$n2" ] && echo OK || echo "LEAK: dedup re-ingested, delta=$((n2-n1))"` (substitute the project's chunk-count / ingest commands; assert delta == 0 and no new embed calls)
- [ ] a per-source freshness cadence (TTL / max-age) is defined AND stale chunks are evicted/superseded on re-sync (no dead content retrievable); the schedule defers to the `cronjob` skill, not a hand-rolled scheduler
- [ ] a citation/attribution policy + quotable-source allowlist is documented, and every chunk has a stable `citation_id` + source URI
- [ ] KB defers chunking/embeddings/indexing to `retriever` — no reimplemented splitter or embeddings client lives in the KB output (`! grep -rEi '(text_?splitter|chunk_?text|embed(dings)?_client|\.encode\(|RecursiveCharacter)' <kb-generated-dir> && echo OK || echo "LEAK: reimplemented retriever infra"`)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v sha256sum` (or an equivalent hashing tool for the dedup step) → note absent, don't fail
- [ ] the `cronjob` skill is available for the re-sync schedule and the `vector_store` SDK is installed → note absent, don't fail
- [ ] a content/PII secret scrubber is present to quarantine sensitive content on the ingest path → note absent, don't fail (the `gitleaks` pre-commit hook does NOT cover this — it scans commits, not corpus ingest)

## Functional
- Ingest a sample source, then mutate it and re-sync: confirm only the CHANGED chunks re-embed (unchanged ones are content-hash no-ops) and the stale prior version is no longer retrievable from the `vector_store`. Confirm a retrieval honors an `acl` pre-filter and that returned chunks resolve to a valid `citation_id` + source URI per the citation policy. The freshness SLI (max age of any served chunk) reconciles with the per-source TTL.
