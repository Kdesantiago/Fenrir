---
name: memory-keeper
description: Use when you want to record or query the in-repo, git-tracked delivery memory (decision notes, gate-exceptions, drift-log, lessons) for THIS repo. NOT a personal-AI memory store, NOT for secrets/personal-data/session-transcripts, NOT for cross-repo aggregation. Writes and reads files under docs/delivery-memory/; every gate waiver carries an owner and a mandatory expiry.
---

# Memory Keeper

Delivery memory is an **in-repo, git-tracked, reviewable** record scoped to delivery. It is NOT a hidden store and NOT a personal-AI memory. Everything it writes lands under the consuming repo's `docs/delivery-memory/` and goes through normal code review.

## When to use
- "record a decision / a drift / a lesson", "note why we picked X"
- "waive gate <rule> until <date>" — document a temporary, expiring deviation from a gate
- "list open exceptions", "what drifted recently"
- "expire / close the lapsed exceptions"
- "recall what we know relevant to <task>" — surface prior decisions, open waivers, lessons before starting work

## When NOT to use
- Personal-AI / cross-session assistant memory, user preferences → not this skill; this is delivery-scoped, in-repo only
- Full architecture decision records (ADRs) → owned by the architect agent; here you write a SHORT note that **links** the ADR, never duplicates it
- Running or enforcing gates → `delivery-gates`; a waiver here does NOT run or disable a gate
- Storing secrets, tokens, credentials, PII, or raw session transcripts → refuse (see Refuses when)
- Aggregating memory across multiple repos → out of scope; this skill only touches the current repo

## Inputs
- The consuming repo root (memory lives at `docs/delivery-memory/` under it)
- The operation: `record` | `waive` | `list` | `expire` | `recall`
- For `record`: kind (`decision` | `drift` | `lesson`) and its payload
- For `waive`: `rule` (which check is waived), `reason`, `granted_by`, and `expires` (default: today + 30 days)
- For `recall`: a task description / keywords to match against existing memory
- Today's date (for default expiry and for expiry filtering)

## Layout (all under the consuming repo)
- `docs/delivery-memory/decisions/` — short decision notes, one Markdown file per decision (e.g. `2026-06-27-postgres-over-dynamo.md`). Lighter than an ADR; link the ADR if one exists.
- `docs/delivery-memory/gate-exceptions.jsonl` — temporary gate waivers, one JSON object per line. A SessionStart hook reads this; **field names are fixed.**
- `docs/delivery-memory/drift-log.jsonl` — append-only log of changes to `org-profile.yaml` / `template_version` / platform.
- `docs/delivery-memory/lessons.md` — recurring review/red-team findings worth feeding back into checks.

### gate-exceptions.jsonl — EXACT per-line schema
`session-context.py` (the SessionStart hook) parses each line and injects OPEN, non-expired exceptions into every session. Do NOT rename, drop, or reorder-out these fields:

```json
{"id": "ge-2026-06-27-001", "rule": "coverage-threshold", "reason": "flaky integration suite, fix tracked in JIRA-1234", "granted_by": "kylliann.desantiago@gmail.com", "expires": "2026-07-27", "status": "open"}
```

- `id` — stable unique id (e.g. `ge-<date>-<n>`).
- `rule` — the exact check being waived (must match how the gate names it).
- `reason` — why; non-empty, no secrets.
- `granted_by` — owner accountable for the waiver.
- `expires` — `YYYY-MM-DD`; **mandatory**. The hook filters by this date.
- `status` — `open` | `closed`.

An exception that is `closed` OR past `expires` is auto-ineligible: the hook never surfaces it, so an expired waiver stops protecting nothing on its own — it simply disappears from sessions and the gate is live again.

## Steps

**record (decision)**
1. Create `docs/delivery-memory/decisions/<YYYY-MM-DD>-<slug>.md`.
2. Capture: context, the decision, alternatives rejected, and a link to the owning ADR if one exists. Keep it short — do not restate ADR content.

**record (drift)**
1. Append one line to `drift-log.jsonl`: `{"when": "<YYYY-MM-DD>", "what": "<org-profile.yaml|template_version|platform> <old> -> <new>", "why": "...", "by": "<owner>"}`.
2. Never edit prior lines; the log is append-only.

**record (lesson)**
1. Append an entry to `lessons.md`: the finding, the class of bug, and the concrete check/gate change that would catch it next time.

**waive**
1. Require `rule`, `reason`, `granted_by`. If `expires` is absent, default to today + 30 days. Refuse a waiver with no reason or no owner.
2. Append exactly one line to `gate-exceptions.jsonl` using the schema above, `status: "open"`, a fresh `id`.
3. State that this does NOT disable the gate — it is a last-resort, expiring, session-visible deviation.

**list**
1. Open exceptions: read `gate-exceptions.jsonl`, print lines where `status == "open"` AND `expires >= today`. Flag any `open` line already past `expires` as "lapsed — run expire".
2. Recent drift: print the last N lines of `drift-log.jsonl`.

**expire**
1. Read `gate-exceptions.jsonl`; for every `open` line with `expires < today` (or one the user names as resolved), rewrite that line with `status: "closed"`.
2. Preserve all other fields and line order. Report which ids were closed.

**recall**
1. Match the task keywords against `decisions/*.md`, open `gate-exceptions.jsonl` entries, recent `drift-log.jsonl`, and `lessons.md`.
2. Return the relevant decisions (with ADR links), any open waiver touching the area, and applicable lessons — so the work starts with the prior context already surfaced.

## Output
- `record`: path of the decision note, or the appended `drift-log`/`lessons` line, echoed back.
- `waive`: the exact JSONL line appended, plus a one-line reminder of its expiry and that the gate stays live.
- `list`: open exceptions (id, rule, owner, expires) and recent drift entries; lapsed-but-still-open ones called out.
- `expire`: the ids closed.
- `recall`: a short digest of relevant decisions, open waivers, and lessons for the task.

## validation
- After any write, the changed file is valid: each `.jsonl` line parses as a single JSON object; `gate-exceptions.jsonl` lines carry all six fields (`id`, `rule`, `reason`, `granted_by`, `expires`, `status`) with `expires` as `YYYY-MM-DD`.
- Re-running `list` reflects the write; the SessionStart hook would surface exactly the `open` + non-expired exceptions.
- All paths are under `docs/delivery-memory/` in the current repo; nothing is written outside it.
- Diffs are reviewable in the normal PR flow — memory is git-tracked, never hidden.

## Refuses when
- Asked to store secrets, tokens, credentials, PII, or raw session transcripts
- Asked to write a gate-exception without a `reason`, without a `granted_by` owner, or without an `expires` date (and unable to default one)
- Asked to change the `gate-exceptions.jsonl` field names/schema the SessionStart hook depends on
- Asked to use this as personal-AI / cross-session assistant memory, or to aggregate memory across repos (out of scope — this repo only)
- Asked to duplicate full ADR content instead of linking it
