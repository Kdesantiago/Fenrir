---
name: data-model
description: Use when DESIGNING or REVIEWING a SQLAlchemy data model / query layer — normalized schema + relationships, indexes from real access patterns, N+1 elimination, keyset pagination, EXPLAIN-backed query review. Triggers — "design this schema", "model these entities", "why is this query slow", "add an index", "fix the N+1". NOT for emitting/applying the Alembic migration (db-migration owns that), NOT for the HTTP layer (api-first), NOT for vector search (retriever). Advisory — every index must name the query it serves. Reads org-profile.yaml `framework`; refuses off-stack.
---

# Data Model — schema, indexes, and query-perf design

This skill **designs and reviews** the ORM model and query layer; it does not author or apply the migration. The schema delta it produces is handed to `db-migration` for the safe, reversible Alembic revision, and the real teeth are couche-0 (the migrate step in CI / the deploy pipeline applies; branch-protection blocks). A skill cannot stop a slow query from shipping — it can only make the index/EXPLAIN evidence a review demands.

## When to use
- "design the schema for X" / "model these entities" — pick NF, keys, relationships, loading strategy
- "this query/endpoint is slow" — diagnose with `EXPLAIN ANALYZE` and fix the access path
- "do I need an index here" — choose indexes from real access patterns, not a hunch
- "fix the N+1 in this list endpoint" — pick `selectinload`/`joinedload` and prove the query-count drop

## When NOT to use
- Emitting or applying the Alembic revision (autogenerate, reversible downgrade, lock-free DDL) → `db-migration` (it scopes ORM modeling/query code OUT; this skill fills exactly that gap)
- HTTP request/response shape, status codes, error envelope → `api-first`
- Vector/embedding similarity search, recall@k → `retriever`

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED; must be a SQLAlchemy stack (`fastapi`). Refuse otherwise — the modeling/query idioms here are SQLAlchemy + Postgres specific.
- The entities/relationships to model, OR the slow query + its access pattern (read/write ratio, cardinality, selectivity, the filter/sort columns)
- Existing ORM models (`models.py` / the `models/` tree) and `EXPLAIN ANALYZE` output for the target query

## Steps
1. **Read `org-profile.yaml`; confirm SQLAlchemy/`fastapi`.** If `framework` is unset or non-SQLAlchemy (`express`, `spring`, `streamlit`, `none`), REFUSE and point to that stack's ORM/query tooling.
2. **Model the schema.** Normalize to the right normal form (3NF default); pick PK/FK, declare each `relationship()` with an explicit `back_populates` and ON DELETE behavior. Denormalize ONLY with a stated read/write justification (e.g. read-heavy, write-rare counter) — never by default.
3. **Index FROM access patterns, not from columns.** For each hot query name the predicate: composite indexes ordered most-selective-first, covering indexes (`Index(..., postgresql_include=[...])`) for index-only scans, partial indexes for sparse filters. REFUSE to add an index that does not name the query it serves (a write-cost with no read).
4. **Eliminate N+1.** Choose the loading strategy per relationship: `selectinload` for collections (one extra query, no row fan-out), `joinedload` for many-to-one, `lazy="raise"` on hot paths to make accidental lazy loads fail loud. Show the before/after query count.
5. **Paginate by keyset, not OFFSET.** Use cursor/keyset pagination (`WHERE (sort_key, id) > (:last_key, :last_id) ORDER BY sort_key, id LIMIT n`) for large collections — OFFSET degrades linearly and skips rows under concurrent writes. Tie cursor shape to the `api-first` list conventions.
6. **Prove it with `EXPLAIN ANALYZE`.** Run every hot query against a representatively-seeded DB; assert the index is used (no unexpected `Seq Scan` on the hot path, no surprise sort/hash-join blowup). Capture the plan as the evidence behind each index.
7. **Hand the schema delta to `db-migration`.** Produce the model change + index DDL intent and route it to `db-migration` for the reviewed, reversible Alembic revision — do NOT write or run the Alembic script here (that is its carve).

## Output / validation
- A reviewed data model (entities, keys, relationships + loading strategy), an index plan where each index cites the query it serves, a keyset-pagination shape for list endpoints, and `EXPLAIN ANALYZE` plans for the hot paths
- Validate: each hot query's plan shows index usage (no unexpected seq scan); the N+1 fix drops the measured query count; list endpoints use keyset, not unbounded OFFSET
- This skill advises and reviews; the schema delta becomes real only once `db-migration` writes the revision and CI / the deploy pipeline applies it — not this skill

## Refuses when
- `framework` is unset in `org-profile.yaml`, or is a non-SQLAlchemy stack (`express`, `spring`, `streamlit`, `none`)
- Asked to add an index that does not name a query/access pattern it serves (a pure write-cost)
- Asked to emit or apply the Alembic migration — that is `db-migration`; this skill stops at the schema delta
- A list/collection endpoint is requested with unbounded OFFSET pagination on a large table (use keyset)
