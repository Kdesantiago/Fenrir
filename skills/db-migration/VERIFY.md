# VERIFY — db-migration

Run after `db-migration` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] stack matches `org-profile.yaml` `framework` (SQLAlchemy/Alembic — `fastapi`) and the Alembic tree exists: `[ -f alembic.ini ] && [ -d alembic/versions ] || ls */alembic/versions >/dev/null 2>&1 && echo OK || echo MISSING`
- [ ] the new revision has a REAL `downgrade()` that reverses `upgrade()` (not a `pass`/`raise NotImplementedError` stub): inspect the latest file in `alembic/versions/`
- [ ] schema change and data backfill are in SEPARATE migrations (schema ships first); concurrent index creation is its own non-transactional migration; DDL is guarded idempotent (`IF NOT EXISTS` where allowed)
- [ ] a single linear head, no divergent branches: `alembic heads | wc -l` returns 1
- [ ] destructive changes (drop column/table, type narrowing) carry an explicit expand→migrate→contract plan — never a bare drop

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v alembic` · a disposable DB (sqlite/postgres) for the round-trip test → note absent, don't fail

## Functional
- On a throwaway DB copy, run `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`; all three succeed cleanly (the migration applies, reverses, and re-applies).
