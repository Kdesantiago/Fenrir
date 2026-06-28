# VERIFY — data-model

Run after `data-model` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] stack matches `org-profile.yaml` `framework` (SQLAlchemy — `fastapi`) and ORM models exist: `grep -qiE '^framework:\s*fastapi' org-profile.yaml && { [ -f models.py ] || ls **/models.py >/dev/null 2>&1 || ls **/models/__init__.py >/dev/null 2>&1; } && echo OK || echo MISSING`
- [ ] every proposed index names the query / access pattern it serves (no index added as a bare column-cost with no read justification)
- [ ] hot-path queries carry `EXPLAIN ANALYZE` output showing index usage — no unexpected `Seq Scan` on the hot path
- [ ] list/collection endpoints use keyset/cursor pagination, not unbounded `OFFSET`, on large tables
- [ ] each modeled `relationship()` declares its loading strategy (`selectinload`/`joinedload`/`lazy="raise"`) — no implicit lazy load on a hot path
- [ ] the schema delta is handed OFF to `db-migration` — no Alembic revision is authored or applied inside this skill (that is db-migration's carve)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v psql` · `python -c "import sqlalchemy"` · `command -v alembic` (the apply sibling) → note absent, don't fail

## Functional
- Against a representatively-seeded DB, run the target endpoint/query and capture the executed SQL: confirm the measured query count matches the design (the N+1 is gone — one query per collection via `selectinload`, not one-per-row) and the `EXPLAIN ANALYZE` plan uses the proposed index with latency in the expected range.
