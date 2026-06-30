# Spec — R8: easy-deploy the dashboard + move the default port off 8000

Status: proposed · Owner: delivery · Date: 2026-06-29

## Problem

Two friction points stop the Fenrir dashboard from being a turnkey companion app:

1. **No one-command launch from the plugin.** Today the only documented way to run it is
   `cd dashboard && uv sync --extra dev && uv run uvicorn backend.app:app --reload`
   (`dashboard/README.md` §Run). That assumes the dashboard **source lives inside the
   consuming repo**. When Fenrir is installed as a *plugin*, the dashboard code is under
   `${CLAUDE_PLUGIN_ROOT}/dashboard`, NOT in the user's repo — so a user must copy the
   `dashboard/` tree into their repo (or `cd` into the plugin cache by hand) to run it. There
   is no `/fenrir:dashboard` command and no launcher script.

2. **Default port is 8000.** `uvicorn ... app:app` binds **8000** by default (the README even
   hardcodes `http://127.0.0.1:8000`). 8000 is the single most collision-prone dev port on a
   developer machine (uvicorn / Django / `python -m http.server` all default to it), so the
   dashboard routinely fails to bind or silently attaches to the wrong server.

## Investigation — current state (ground truth)

| Concern | What the code does today | File:line |
| --- | --- | --- |
| Frontend → backend URL | **Same-origin, relative.** `api(path)` calls `fetch(path)` with `path` = `"/api/..."`; header comment says *"Endpoints (all same-origin)"*. **No host/port is ever hardcoded in JS.** | `dashboard/frontend/app.js:2`, `:73-74`; `index.html` loads `app.js` relatively |
| Backend bind port | Not set in app code — inherited from **uvicorn's 8000 default** via the README run command. `app.py` has no `PORT`/host handling. | `dashboard/backend/app.py:3` (docstring), `dashboard/README.md:16` |
| Only literal `8000` in the repo | **One place:** the README "Then open `http://127.0.0.1:8000`". (Grep for `8000` elsewhere hits only a `80000` **token count** in a test — not a port.) | `dashboard/README.md:19` |
| `FENRIR_DASH_PORT` | **Does not exist** anywhere. | — |
| Board DATA location | Per-project file **inside the dashboard dir**: `config.board_path()` → `dashboard/data/boards/<slug>.json`, where `<slug>` is `telemetry.current_project_slug()` (auto-detected from the **git root of the process cwd**). `FENRIR_DASH_BOARD` env pins an explicit file and **wins** over the slug. | `dashboard/backend/config.py:35-39`, `:53-55`; `dashboard/backend/telemetry.py:100-115` |
| Board-data contract (writer) | `scripts/track_session.py` resolves the board by asking the dashboard's own resolver (`config.board_path()`), honoring `FENRIR_DASH_BOARD`; it reads the board read-only and mutates only through `python -m backend.cli`. Same `BoardStore` as the web API → one source of truth. | `scripts/track_session.py:69-85`, `:163-191` |
| Telemetry source | Read-only over `~/.claude` (override `FENRIR_DASH_CLAUDE_DIR`); project auto-scoped to the cwd's git repo. | `dashboard/backend/telemetry.py:23`, `:100-115` |
| Cross-OS launcher precedent | `hooks/run-python.sh` probes `python3 → python → py -3` and `exec`s the first real interpreter; commands invoke `python3 "$CLAUDE_PLUGIN_ROOT/scripts/<x>.py"` (see `commands/status.md:25`). Plugin substitutes `${CLAUDE_PLUGIN_ROOT}` on every OS. | `hooks/run-python.sh`, `commands/status.md:22-29` |

### Key consequences for the design

- **The frontend needs ZERO changes.** It is already origin-relative, so whatever port the
  backend binds, the SPA served from that same origin reaches `/api/*` automatically. The
  "derive the backend URL from the served origin" requirement is **already satisfied**; we
  must only avoid *re-introducing* a hardcoded port (and fix the one stale README mention).
- **"Without copying code into the user's repo" is achievable by running the bundled backend
  with its cwd = the consuming repo.** Because the board slug and the telemetry project are
  auto-detected from the **process cwd's git root**, a launcher that lives in the plugin but
  is invoked from the user's repo (passing `cwd` or `--repo`) resolves the user's board/project
  while executing the plugin's code. The board JSON stays under `dashboard/data/boards/<slug>.json`
  unless `--board`/`FENRIR_DASH_BOARD` redirects it into the repo.

## Design

### 1. One-command launch (no copy into the repo)

Add a **pure-stdlib, cross-OS launcher** and a thin **slash command** that calls it.

#### A. `scripts/dashboard.py` (new, pure stdlib)

A stdlib-only launcher that lives in the plugin and starts the bundled backend. Responsibilities:

1. **Locate the bundled dashboard:** `dash = ${FENRIR_DASH_DIR or <plugin_root>/dashboard}`,
   where `<plugin_root>` is `os.environ["CLAUDE_PLUGIN_ROOT"]` or, as a fallback, the parent of
   `scripts/` (`Path(__file__).resolve().parent.parent`). Refuse (exit 0, print skip) if
   `dash/backend` is absent — mirrors the fail-open hooks.
2. **Resolve the interpreter cross-OS** (same discipline as `run-python.sh`): prefer the
   dashboard's own venv (`dash/.venv/bin/python` POSIX, `dash/.venv/Scripts/python.exe` Windows —
   reuse the exact logic from `track_session._dash_python`), else probe `python3 → python → py -3`
   on `PATH`, else the current `sys.executable`.
3. **Point the backend at the consuming repo's board/telemetry WITHOUT copying code:** default
   the process **cwd to the user's repo** (`--repo`, default = `CLAUDE_PROJECT_DIR` or the
   original `os.getcwd()` *before* we chdir into the plugin) so `current_project_slug()` resolves
   the user's project. Pass `--board PATH` → exported as `FENRIR_DASH_BOARD`; pass
   `--claude-dir` → `FENRIR_DASH_CLAUDE_DIR`. All optional; the env still wins.
4. **Pick the port** (see §2): `--port` arg → else `FENRIR_DASH_PORT` env → else **8765**.
   If the chosen port is busy, probe upward (8765→8766→…, max +20) and print the real bound port.
5. **Start the server** via the dashboard's venv interpreter:
   `python -m uvicorn backend.app:app --host 127.0.0.1 --port <port>` run with `cwd=dash` and the
   repo passed through env so the board resolver still sees it (export `CLAUDE_PROJECT_DIR=<repo>`).
   If uvicorn import fails (no deps installed), **fall back to nothing** — print a one-line
   `uv sync` hint and exit non-zero (the backend genuinely needs FastAPI/uvicorn; a stdlib
   `http.server` cannot serve the API). The launcher itself stays stdlib; only the *served app*
   needs the venv.
6. **Open the browser** (best-effort): `webbrowser.open(f"http://127.0.0.1:{port}")` after a short
   delay; suppress on `--no-browser`. Print the URL regardless.

Exact invocation the command runs:

```sh
python3 "$CLAUDE_PLUGIN_ROOT/scripts/dashboard.py" --repo "$CLAUDE_PROJECT_DIR"
# optional:  --port 8765   --board ./.fenrir/board.json   --no-browser
```

(Per launcher-pass-1 discipline, the command line uses `python3` exactly as `commands/status.md`
does; `dashboard.py` re-resolves a working interpreter internally for the uvicorn child so a host
without `python3` on `PATH` still works.)

#### B. `commands/dashboard.md` (new) → `/fenrir:dashboard`

Frontmatter `description:` one-liner; body runs the launcher above and explains: it serves the
**bundled** dashboard from the plugin, scoped to the current repo's board/telemetry, on
`http://127.0.0.1:<port>` (default 8765), no files copied into the repo. Documents `--port`,
`--board`, `--no-browser`, `FENRIR_DASH_PORT`, `FENRIR_DASH_BOARD`. Mirrors `status.md`'s
`$CLAUDE_PLUGIN_ROOT` fallback note.

> The frontend reaches the backend over the **served origin** (`window.location`) — it already
> uses relative `/api/*` fetches (`app.js:73`), so it works on any port with **no JS change**.

### 2. Default port off 8000 → **8765** (env/flag overridable)

**Chosen default: `8765`.** Collision check: 8000 (uvicorn/Django/http.server), 8080 (Tomcat/alt-HTTP),
3000 (Node/Vite/React), 5000 (Flask/AirPlay-macOS), 8888 (Jupyter), 9000 (PHP-FPM/SonarQube) are the
common dev defaults — **8765 is none of them** and is not a registered well-known service, so it is
unlikely to collide. Alternatives if rejected: **8420**, **7777** (both also uncommon). The launcher
auto-increments on a busy port, so a rare clash degrades gracefully.

Resolution order (highest wins): `--port` flag → `FENRIR_DASH_PORT` env → `8765`.

### File-by-file change list

| File | Change |
| --- | --- |
| `scripts/dashboard.py` | **NEW.** Pure-stdlib cross-OS launcher (§1.A): resolve plugin root + interpreter, set repo cwd / `FENRIR_DASH_BOARD` / `FENRIR_DASH_CLAUDE_DIR`, pick port (flag → `FENRIR_DASH_PORT` → 8765, auto-increment if busy), spawn `uvicorn backend.app:app --host 127.0.0.1 --port <port>` with `cwd=<dash>`, open browser. Fail-open skip when `dash/backend` absent. |
| `commands/dashboard.md` | **NEW.** `/fenrir:dashboard` command (§1.B) wrapping the launcher; documents flags/env and the no-copy, repo-scoped behavior. |
| `dashboard/backend/app.py` | Update the module docstring **`:3`** `Run:` line from `uvicorn backend.app:app --reload` to reference port `8765` (e.g. `uvicorn backend.app:app --port 8765 --reload`) and add `FENRIR_DASH_PORT` to the `Env:` block (**`:4-6`**). No code change — port stays a uvicorn arg the launcher supplies. |
| `dashboard/README.md` | **`:13-19`** (§Run) — replace the manual `cd dashboard && uvicorn …` snippet's port-less form + the hardcoded **`http://127.0.0.1:8000`** with: (a) the one-command `/fenrir:dashboard` (or `python3 "$CLAUDE_PLUGIN_ROOT/scripts/dashboard.py"`) path as the primary way, (b) the manual fallback shown as `uv run uvicorn backend.app:app --port 8765 --reload` → open **`http://127.0.0.1:8765`**. Add `FENRIR_DASH_PORT` (default `8765`) to the **Environment variables** table (**`:23-27`**). |
| `docs/specs/dashboard-easy-deploy.md` | This spec (artifact). |

### Explicitly NO change required

- `dashboard/frontend/app.js` / `index.html` — already origin-relative (`app.js:2`, `:73-74`);
  the SPA derives the backend URL from `window.location`. **Do not** hardcode any port here.
- `dashboard/backend/config.py`, `board.py`, `telemetry.py` — board/telemetry resolution is
  unchanged; the launcher only sets cwd + the existing `FENRIR_DASH_BOARD`/`FENRIR_DASH_CLAUDE_DIR`
  envs they already honor.
- No test or e2e fixture references port 8000 (the former Playwright suite is deleted; the only
  `8000`-ish grep hit, `test_cost_accounting.py:165`, is the integer `80000` token count).

## Acceptance criteria

1. `/fenrir:dashboard` (and `python3 "$CLAUDE_PLUGIN_ROOT/scripts/dashboard.py" --repo <repo>`) starts
   the bundled backend from `${CLAUDE_PLUGIN_ROOT}/dashboard` with **no files copied** into `<repo>`,
   and the board/telemetry it shows is scoped to `<repo>`'s project (or `--board`).
2. The server binds **8765** by default; `--port`/`FENRIR_DASH_PORT` override it; a busy default
   auto-increments and the launcher prints the real bound URL.
3. The browser opens `http://127.0.0.1:<port>` and the SPA loads data from that same origin (no
   `8000`, no hardcoded host anywhere in JS).
4. `grep -rn '8000' dashboard/ scripts/ commands/` returns no **port** usage (only the `80000`
   token count remains).
5. Launcher is pure stdlib and runs on macOS/Linux/Windows (interpreter probed like `run-python.sh`).

## Open question

Default port **8765** — confirm acceptable (recommended; alternatives 8420 / 7777).
