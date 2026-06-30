---
description: Launch the bundled Fenrir dashboard (telemetry + Agile board) for THIS repo with one command — no files copied into the repo, served on http://127.0.0.1:8765 by default. Cross-OS stdlib launcher; auto-picks a free port and opens your browser.
---

# /fenrir:dashboard

Starts the **bundled** dashboard that ships inside the Fenrir plugin, scoped to the
current repo's board + telemetry. Nothing is copied into your repo — the launcher runs
the plugin's own backend (with cwd = the plugin's `dashboard/`, so it can import) but passes
**your** repo through `CLAUDE_PROJECT_DIR`, and the backend keys board/telemetry detection off
that path's git root (not the process cwd). It also pins the computed board via
`FENRIR_DASH_BOARD` so resolution is unambiguous. Open the printed URL to see the Agile board
and cost/telemetry views.

## Run it
```sh
# Serves the bundled dashboard for $CLAUDE_PROJECT_DIR on http://127.0.0.1:8765
python3 "$CLAUDE_PLUGIN_ROOT/scripts/dashboard.py" --repo "$CLAUDE_PROJECT_DIR"

# Options:
#   --port 9000               pick the bind port (default: FENRIR_DASH_PORT or 8765)
#   --board ./.fenrir/board.json   pin an explicit board file (else per-project default)
#   --claude-dir /path/.claude     override the ~/.claude dir scanned for telemetry
#   --no-browser              don't auto-open a browser
```
If `$CLAUDE_PLUGIN_ROOT` is unset (rare), resolve the plugin root from where this command
lives. The command line uses `python3` exactly like `/fenrir:status`; the launcher itself
is pure stdlib and re-resolves a working interpreter (the dashboard's `.venv`, else
`python3 → python → py -3`) for the uvicorn child, so a host without `python3` on `PATH`
still works.

## Behavior
- **No code copied.** The backend runs from `${CLAUDE_PLUGIN_ROOT}/dashboard`; the repo path
  is passed in via `CLAUDE_PROJECT_DIR` (and the resolved board via `FENRIR_DASH_BOARD`), so the
  board JSON and telemetry shown are scoped to **your** project, not the plugin's — the backend
  resolves the project from `CLAUDE_PROJECT_DIR`'s git root, never from its own working dir.
- **Default port 8765**, off the common dev defaults (8000/8080/3000/5000/8888/9000). A busy
  port auto-increments (8765 → 8766 → …, up to +20) and the launcher prints the real URL.
- **Origin-relative frontend.** The SPA reaches the API over the served origin
  (`window.location` → relative `/api/*` fetches), so it works on whatever port bound — no
  configuration, no hardcoded host.
- **Fail-open.** If the bundled dashboard is absent (plugin not fully installed), it prints
  a skip line and exits cleanly. If the dashboard deps are missing on a fresh checkout, it
  hints `uv sync --extra dev`.

## Environment
| Variable | Default | Purpose |
| --- | --- | --- |
| `FENRIR_DASH_PORT` | `8765` | Bind port (the `--port` flag overrides it). |
| `FENRIR_DASH_BOARD` | *(per-project)* | Explicit board JSON path (`--board` sets this). |
| `FENRIR_DASH_CLAUDE_DIR` | `~/.claude` | Telemetry source dir (`--claude-dir` sets this). |

Manual fallback (from a checkout that has the dashboard source):
```sh
cd dashboard && uv run uvicorn backend.app:app --port 8765 --reload
# then open http://127.0.0.1:8765
```
