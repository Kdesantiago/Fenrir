# Fenrir Dashboard

A local monitoring web app for Fenrir. It does two things:

1. **Telemetry** — parses your real Claude Code transcripts under `~/.claude` and aggregates agent / token / cost activity (by model, skill, day, and source: main thread vs subagent). Read-only; it never mutates the logs.
2. **Agile board** — an `Epic → Feature → User Story → Task` kanban that the agents drive themselves via a CLI. The board is plain, git-trackable JSON (`data/board.json`), and stories/tasks cross-link to real telemetry through their `work_log`.

> This is a **companion app**, not a plugin component. It has its own dependencies, its own CI job, and runs standalone.

## Run

```bash
cd dashboard
uv sync --extra dev
uv run uvicorn backend.app:app --reload
```

Then open <http://127.0.0.1:8000>. The JSON API lives under `/api/*`; a static SPA is served from `frontend/` if that directory exists (the API always takes precedence over the static mount).

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `FENRIR_DASH_BOARD` | `data/board.json` | Path to the board JSON store. |
| `FENRIR_DASH_CLAUDE_DIR` | `~/.claude` | Override the Claude Code directory scanned for telemetry. |
| `FENRIR_DASH_PROJECT` | *(all)* | Restrict telemetry to a single `~/.claude/projects/<name>` directory. Unset = scan every project. |

## How agents drive the board

Agents mutate the board through the CLI (run from `dashboard/`). It goes through the same `BoardStore` as the web API, so there is one source of truth. Every mutating command prints the resulting object as JSON, so an agent can parse the result.

```bash
# create an epic
python -m backend.cli epic add --title "Monitoring dashboard"

# add a feature under it
python -m backend.cli feature add --epic epic-1 --title "Telemetry view"

# add a user story under a feature
python -m backend.cli story add --feature feat-1 --title "Cost by model" \
    --assignee architect --points 3 \
    --as-a "tech lead" --i-want "cost per model" --so-that "I can budget" \
    --ac "shows USD per model" --ac "refreshes on load"

# add a task under a story
python -m backend.cli task add --story us-1 --title "wire the chart" --assignee coder

# move an item across columns
python -m backend.cli move --kind story --id us-1 --status in_progress

# (re)assign an agent (stories and tasks only)
python -m backend.cli assign --kind story --id us-1 --agent coder

# log real work against an item (stories and tasks only)
python -m backend.cli log --kind story --id us-1 --agent coder \
    --in-tokens 1200 --out-tokens 800 --cost 0.05 --note "first pass"

# print the whole board as a tree
python -m backend.cli list

# delete (cascades to children)
python -m backend.cli delete --kind feature --id feat-1
```

### CLI flags

- `epic add` — `--title` (required), `--description`, `--color` (default `#6366f1`)
- `feature add` — `--epic` (required), `--title` (required), `--description`
- `story add` — `--feature` (required), `--title` (required), `--assignee`, `--points` (int), `--as-a`, `--i-want`, `--so-that`, `--ac` (repeatable, one acceptance criterion each)
- `task add` — `--story` (required), `--title` (required), `--assignee`
- `move` — `--kind` (required), `--id` (required), `--status` (required: `backlog`, `todo`, `in_progress`, `review`, `done`, `blocked`)
- `assign` — `--kind` (required), `--id` (required), `--agent` (required) — stories/tasks only
- `log` — `--kind` (required), `--id` (required), `--agent`, `--session`, `--in-tokens` (int), `--out-tokens` (int), `--cost` (float), `--note`, `--at` (ISO timestamp; defaults to now) — stories/tasks only
- `delete` — `--kind` (required), `--id` (required) — cascades to children
- `list` — no flags

`--kind` is one of `epic`, `feature`, `story`, `task`.

## API surface

Board:

- `GET  /api/health` — liveness check
- `GET  /api/board` — full board (epics, features, stories, tasks)
- `POST /api/epics` · `POST /api/features` · `POST /api/stories` · `POST /api/tasks` — create
- `PATCH /api/{kind}/{id}/status` — move (body: `{"status": ...}`)
- `PATCH /api/{kind}/{id}/assign` — assign (body: `{"assignee": ...}`; stories/tasks only)
- `POST  /api/{kind}/{id}/worklog` — append a work-log entry (stories/tasks only)
- `DELETE /api/{kind}/{id}` — delete (cascades)

Telemetry (all read-only aggregations over `~/.claude`):

- `GET /api/telemetry/summary` — totals: calls, tokens, cache, cost, models, sessions, date range
- `GET /api/telemetry/by-model` — cost/tokens grouped by model
- `GET /api/telemetry/by-skill` — grouped by attributed Fenrir skill
- `GET /api/telemetry/by-day` — daily tokens + cost
- `GET /api/telemetry/agents` — "who spent what": split by source (main vs subagent) and by skill

## Data model

The board is a strict hierarchy (Pydantic v2 models in `backend/models.py`):

```
Epic (epic-N)
  └─ Feature (feat-N)        epic_id
       └─ UserStory (us-N)   feature_id  · assignee · points · as_a/i_want/so_that · acceptance_criteria · work_log
            └─ Task (task-N) story_id    · assignee · work_log
```

- **Status** (all items): `backlog`, `todo`, `in_progress`, `review`, `done`, `blocked`. The kanban renders the first five as columns.
- **Assignee** (stories/tasks): an agent name, e.g. `architect`, `coder`, `reviewer`.
- **WorkLogEntry**: `agent`, `session_id`, `input_tokens`, `output_tokens`, `cost_usd`, `note`, `at` (ISO timestamp). This is how an item links to real agent activity.
- IDs are auto-assigned with a per-kind prefix (`epic-`, `feat-`, `us-`, `task-`) and a collision-safe numeric suffix.

Telemetry events are normalized from each assistant message line in `~/.claude` transcripts: `model`, `usage` (input/output/cache tokens), `timestamp`, `sessionId`, `isSidechain` (subagent vs main), and `attributionSkill` / `attributionPlugin`.

## Cost is an estimate

Claude Code logs **tokens, not dollars** — so cost is **derived**. The price book lives in `backend/pricing.py` (per-1M-token rates for input / output / cache-write / cache-read, resolved by model family). The defaults are public list-price ballparks; **adjust them to your contract**. Unknown models fall back to the Sonnet rate. Treat the reported cost as an estimate, not an invoice.
