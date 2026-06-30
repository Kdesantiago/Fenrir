# Fenrir Dashboard

A local monitoring web app for Fenrir. It does two things:

1. **Telemetry** — parses your real Claude Code transcripts under `~/.claude` and aggregates agent / token / cost activity (by model, skill, day, and source: main thread vs subagent). **Scoped to the current repo's project by default** (a header selector / `?project=` switches between projects, or `all`). Read-only; it never mutates the logs.
2. **Agile board** — an `Epic → Feature → User Story → Task` kanban that the agents drive themselves via a CLI. The board is plain, git-trackable JSON (`data/board.json`), and stories/tasks cross-link to real telemetry through their `work_log`.
3. **Cost accounting** — answer *"what did this User Story cost?"*: per-US (and Feature/Epic) input/output tokens + USD, broken down **per agent**, a chronological **cost trace**, and **subagent attribution** (which named subagent ran, when, on what, how much — reconciled, no double-count). See [Track the cost of a User Story](#track-the-cost-of-a-user-story).

> This is a **companion app**, not a plugin component. It has its own dependencies, its own CI job, and runs standalone. **Cost is a derived estimate** (token×price-book), not billed dollars.

## Run

**One command, no copy** — from any repo where the Fenrir plugin is installed:

```sh
/fenrir:dashboard
# or directly:  python3 "$CLAUDE_PLUGIN_ROOT/scripts/dashboard.py" --repo "$CLAUDE_PROJECT_DIR"
```

This serves the **bundled** dashboard from the plugin, scoped to the current repo's board
and telemetry, on <http://127.0.0.1:8765> — **without copying the `dashboard/` tree into
your repo**. A busy port auto-increments (8765 → 8766 → …) and the launcher prints the real
URL; pass `--port` / `FENRIR_DASH_PORT` to choose one, `--no-browser` to skip opening a tab.

**Zero-install — first launch auto-installs deps.** This `.venv` is gitignored, so a fresh
checkout has no FastAPI/uvicorn. You do **not** need to run `uv sync` yourself: the launcher
detects the missing venv on the first run, prints
`first run: installing dashboard deps via uv sync…`, runs `uv sync` to build the venv, then
serves on it. The sync is gated behind a fast import probe, so it happens **once** — warm
launches reuse the venv and start instantly, never re-syncing. The one prerequisite is `uv`
on `PATH`; if it's missing the launcher tells you to install `uv` (or run the manual step
below) and exits non-zero rather than crashing.

**Manual fallback** (optional — only if you want to run the backend directly, e.g. with
`--reload` for development; the `/fenrir:dashboard` launcher already auto-syncs):

```bash
cd dashboard
uv sync --extra dev
uv run uvicorn backend.app:app --port 8765 --reload
```

Then open <http://127.0.0.1:8765>. The JSON API lives under `/api/*`; a static SPA is served from `frontend/` if that directory exists (the API always takes precedence over the static mount). The SPA reaches the API over the **served origin** (`window.location` → relative `/api/*`), so it works on whatever port bound — no hardcoded host.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `FENRIR_DASH_PORT` | `8765` | Bind port used by `/fenrir:dashboard` (the `--port` flag overrides it; a busy port auto-increments). |
| `FENRIR_DASH_BOARD` | `data/board.json` | Path to the board JSON store. |
| `FENRIR_DASH_CLAUDE_DIR` | `~/.claude` | Override the Claude Code directory scanned for telemetry. |
| `FENRIR_DASH_PROJECT` | *(auto: current repo)* | Pin telemetry to one `~/.claude/projects/<name>`. Unset → the dashboard auto-detects the current repo's project; the UI selector / `?project=<slug>` overrides per request (`all` = every project). |

## Track the cost of a User Story

The dashboard's headline workflow — represent work as a US, then attribute the real spend
to it (the `us-cost-tracking` skill drives this for agents):

```bash
cd dashboard
# 1. represent the work
python -m backend.cli epic add    --title "Checkout v2"
python -m backend.cli feature add --epic epic-1 --title "Payment API"
python -m backend.cli story add   --feature feat-1 --title "Refund endpoint" --assignee architect --points 3

# 2. move it as you work
python -m backend.cli move --kind story --id us-1 --status in_progress

# 3. record REAL cost from a Claude Code session
#    (pulls actual tokens/cost from ~/.claude; idempotent per session; one entry per source)
python -m backend.cli link --kind story --id us-1 --session <session-id>

# 4. read what it cost
python -m backend.cli trace --us us-1
```

- **Per-US / per-agent cost:** `GET /api/board/costs` (or the story modal in the UI) shows
  each US's input/output tokens + USD, broken down by agent, rolled up to Feature and Epic.
- **Cost trace:** `cli trace` / `GET /api/trace?us=<id>&feature=<id>&epic=<id>` — every cost event, filterable by US/Feature/Epic, **newest-first** by default (`--oldest-first` / sort-by-cost optional).
- **Why cache-read looks huge (usually not a leak):** the **Cache efficiency** panel shows a **Re-read / call** figure — cache-read is your *context* (system prompt + every loaded tool/MCP schema + conversation history) re-read on **every** model call at 0.1× input price. Total cache-read ≈ (avg per call) × (number of calls), so it grows with session length and loaded tools, not a bug. Caching saves ~10× **on the read leg only** — cache *writes* cost 1.25–2× input, so a session whose prefix keeps changing (prefix churn) can show **negative savings**, which the panel flags as a warning rather than reassurance. The per-call figure is a blended average over main + subagent calls (cold/first calls pull it below steady-state). To shrink read volume, disconnect MCP servers you aren't using.
- **Subagent attribution:** `GET /api/telemetry/subagents` (or the **Subagents** panel) —
  which named subagent ran, when, on what model, how long, and how much. It **reconciles**:
  `attributed_tokens + unattributed_tokens == subagent_total_tokens` (no double-count;
  identity comes from `agent-*.meta.json`, tokens from the subagent's own transcript).

Cost is a **derived estimate** (token × price book), not an invoice.

## Automatic + enforced tracking (plugin hooks)

The board can be driven by hand (below), but the Fenrir plugin also keeps it populated
**automatically** so work is never left untracked:

- **Auto-create + auto-attribute.** A `SessionEnd` hook (`tracking-finalize`) ensures the
  session has a User Story (creating a catch-all under an `Auto-tracked sessions` epic if
  needed) and links the session's **real** token/USD cost to it. A `SubagentStop` hook
  (`tracking-collect`) ledgers each subagent run for precise per-run attribution.
- **Obligatory.** A `PreToolUse` hook (`tracking-guard`) gates `git commit`: by default it
  auto-creates a US (never blocks); with `FENRIR_TRACK_ENFORCE=strict` it **denies** an
  untraced commit. The authoritative gate is the CI `delivery-trace` check (a PR can't merge
  unless it references a US on the board).
- **Smart breakdown.** The `delivery-tracker` subagent re-parents/re-titles the catch-all US
  into the right `Epic → Feature → US → Task` structure and splits cost per-run when a session
  spanned several US.

The deterministic engine is `scripts/track_session.py` (in the plugin); it reads this board
read-only and mutates it **only** through the CLI below. No `dashboard/` present → the hooks
fail-open (no-op). Knobs: `FENRIR_TRACK_ENFORCE=strict`, `FENRIR_TRACK_DISABLE=1`.

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

# link REAL telemetry into a work_log — pulls actual tokens/cost from ~/.claude
# (filter by session and/or skill; defaults to the current repo's project)
python -m backend.cli link --kind story --id us-1 --session <session-id>
python -m backend.cli link --kind story --id us-1 --skill fenrir:deliver
# project slugs start with "-", so argparse needs the = form: --project=-Users-...-Fenrir

# read the cost trace (flattened work_log, chronological); --us filters to one story
python -m backend.cli trace --us us-1

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
- `link` — `--kind` (required), `--id` (required), `--session`, `--skill`, `--project` (default: current repo; use `--project=<slug>`), `--agent`, `--note` — **whole-session** attribution: sums REAL telemetry matching the filters into work_log entries (**one per source**: main vs subagent). **Idempotent** per `(session, item)`. Stories/tasks only.
- `attribute` — `--kind` (required), `--id` (required), `--run <run_id>` (required; `agent-<id>` from the Subagents view / `/api/telemetry/subagents`), `--project`, `--agent`, `--note` — **per-run** attribution: attaches ONE subagent run's real tokens/cost to a US (distinct per run). Idempotent per `(run_id, US)`. Stories/tasks only.
- `trace` — `--us` (optional, filter to one story) — print the chronological cost trace (flattened work_log) with a total

> **`link` vs `attribute`:** `link` charges a *whole session* to one US (coarse — don't link the
> same session to two US, or both get the same lump). `attribute` charges *one subagent run*
> (precise — different runs give different US different real costs). They are **mutually
> exclusive per session**: once a session has per-run attributions, `link` on it is refused,
> and vice-versa, so the same spend is never counted twice.
- `delete` — `--kind` (required), `--id` (required) — cascades to children
- `list` — no flags

`--kind` is one of `epic`, `feature`, `story`, `task`.

## API surface

Board:

- `GET  /api/health` — liveness check
- `GET  /api/board` — full board (epics, features, stories, tasks)
- `GET  /api/board/costs` — per Epic/Feature/US cost rollup with per-agent breakdown
- `GET  /api/board/flow` — flow metrics (cycle time, weekly throughput, WIP + aging, Monte-Carlo forecast)
- `GET  /api/trace?us=<id>` — chronological cost trace (flattened work_log; `us` optional)
- `POST /api/epics` · `POST /api/features` · `POST /api/stories` · `POST /api/tasks` — create
- `PATCH /api/{kind}/{id}/status` — move (body: `{"status": ...}`)
- `PATCH /api/{kind}/{id}/assign` — assign (body: `{"assignee": ...}`; stories/tasks only)
- `POST  /api/{kind}/{id}/worklog` — append a work-log entry (stories/tasks only)
- `DELETE /api/{kind}/{id}` — delete (cascades)

Telemetry (all read-only aggregations over `~/.claude`). Every endpoint accepts `?project=<slug>` (omit = current repo; `all` = every project):

- `GET /api/projects` — available project slugs + the auto-detected active one
- `GET /api/telemetry/summary` — totals: calls, tokens, cache, cost, models, sessions, date range, plus the active `scope`
- `GET /api/telemetry/by-model` — cost/tokens grouped by model
- `GET /api/telemetry/by-skill` — grouped by attributed Fenrir skill
- `GET /api/telemetry/by-day` — daily tokens + cost
- `GET /api/telemetry/agents` — "who spent what": split by source (main vs subagent) and by skill
- `GET /api/telemetry/subagents` — per-subagent runs (type · when · model · tokens · cost · duration · status) + by-type rollup + the attributed/unattributed reconciliation

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
- **WorkLogEntry**: `agent`, `subagent_type`, `session_id`, `input_tokens`, `output_tokens`, `cost_usd`, `source` (`manual` | `telemetry-link`), `note`, `at` (ISO timestamp). This is how an item links to real agent activity; `cli link`/`trace` and `/api/board/costs` read it.
- IDs are auto-assigned with a per-kind prefix (`epic-`, `feat-`, `us-`, `task-`) and a collision-safe numeric suffix.

Telemetry events are normalized from each assistant message line in `~/.claude` transcripts: `model`, `usage` (input/output/cache tokens), `timestamp`, `sessionId`, `isSidechain` (subagent vs main), and `attributionSkill` / `attributionPlugin`.

## Cost is an estimate

Claude Code logs **tokens, not dollars** — so cost is **derived** (`backend/pricing.py`). The
price book stores a base `(input, output)` rate per model family; cache rates are **derived**
from the input rate via shared multipliers, so a contract change is one number:

| Component | Source field | Rate |
| --- | --- | --- |
| fresh input | `input_tokens` | input |
| output **(incl. extended-thinking tokens — billed as output, no separate field)** | `output_tokens` | output |
| cache **write 5-min** | `cache_creation.ephemeral_5m_input_tokens` | 1.25× input |
| cache **write 1-hour** | `cache_creation.ephemeral_1h_input_tokens` | 2.0× input |
| cache **read** | `cache_read_input_tokens` | 0.1× input |

Defaults are public list-price ballparks — **adjust `PRICES` to your contract**. Unknown models
fall back to the Sonnet rate. **Not modeled** (documented gaps): web-search `server_tool_use`
requests, batch/priority `service_tier` discounts, and the `[1m]` long-context premium (the
suffix is stripped to match the family). Treat the reported cost as an estimate, not an invoice.
