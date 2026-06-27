---
name: db-migration
description: Use when you need a SAFE schema migration for a SQLAlchemy/Alembic service (the org's rag_ingest_api/alembic) — autogenerate then human-review, reversible downgrade, lock-free DDL, backfill split from schema, idempotent, tested up→down→up. NOT for ORM model authoring or app data access (framework generators). Reads org-profile.yaml `framework` and refuses on non-SQLAlchemy stacks. It writes/reviews migration scripts; the migrate step in CI/the deploy pipeline applies them.
---

# DB Migration

## When to use
- "add/alter a column", "create an index", "backfill a table" on a Python/SQLAlchemy service
- The repo has an `alembic/` tree (e.g. `rag_ingest_api/alembic`) and `framework: fastapi`
- You want the expand/contract discipline applied to a risky schema change before it merges

## When NOT to use
- Authoring ORM models / application query code → use the framework/app generator
- A non-SQLAlchemy stack (`express`, `spring`, `streamlit`, `none`) → this skill refuses; use that stack's migration tool
- Running migrations in an environment → the migrate step in CI / the deploy pipeline applies them; this skill only writes and reviews the scripts

## Inputs
- `org-profile.yaml` → `framework` (REQUIRED; must be a SQLAlchemy/Alembic stack — `fastapi`)
- The Alembic env (`alembic.ini`, `alembic/env.py`, `alembic/versions/`) and the target table's current model/DDL
- The intended change (column add/alter/drop, index, backfill) and its expand/contract phase

## Steps
1. Read `org-profile.yaml`; confirm `framework` is a SQLAlchemy/Alembic stack. If not, REFUSE.
2. Classify the change. If it DROPs a column/table or is otherwise destructive, require an explicit deprecate-first (expand → migrate → contract) plan; without one, REFUSE.
3. `alembic revision --autogenerate`, THEN human-review the diff — autogen misses data moves, column/table renames (it sees drop+add), and server defaults. Fix the script by hand.
4. Write a real `downgrade()` that reverses `upgrade()` (reversible). If the change cannot be cleanly reversed, REFUSE until a reversal path exists.
5. Keep DDL lock-light: create indexes `CONCURRENTLY` (and split that into its own non-transactional migration), avoid rewriting large tables in one statement, batch any backfill.
6. Put data backfill in a SEPARATE migration from the schema change (schema migration ships first, then the backfill).
7. Make each migration idempotent / re-runnable (guard with `IF NOT EXISTS` / existence checks where the DDL allows).
8. Test up→down→up on a disposable copy of the DB before merge; the migration must apply, reverse, and re-apply cleanly.

## Output / validation
- One or more reviewed Alembic revisions: schema change and backfill split, each with a working `downgrade()`
- Verify: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` all succeed on a throwaway DB copy
- `alembic history`/`heads` shows a single linear head (no divergent branches)
- This skill authors and verifies the scripts; CI / the deploy pipeline runs `alembic upgrade` as the enforced apply step, not this skill

## Refuses when
- `framework` is unset or not a SQLAlchemy/Alembic stack
- A destructive change (drop column/table, type narrowing) is requested without an explicit expand/contract (deprecate-first) plan
- The migration has no `downgrade()`, or its downgrade does not actually reverse the upgrade
