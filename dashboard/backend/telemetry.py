"""Parse real Claude Code telemetry from ~/.claude transcripts.

Each assistant message line carries `message.model`, `message.usage`
(input/output/cache tokens), a `timestamp`, `sessionId`, `isSidechain` (subagent vs
main thread), and `attributionSkill`/`attributionPlugin` (which Fenrir skill spent the
tokens). We normalize those into events and aggregate by model / skill / day / source /
session — deriving USD cost from the price book. Read-only; never mutates the logs.
"""
from __future__ import annotations

import json
import os
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from . import pricing


def default_claude_dir() -> Path:
    return Path.home() / ".claude"


def _since() -> str:
    """Optional consumption floor: events/runs before `FENRIR_DASH_SINCE` are ignored, so the
    dashboard tracks only from a chosen date forward (transcripts stay intact). Accepts a date
    (`2026-06-29`) or a full ISO timestamp. Empty/unset → no floor."""
    return (os.environ.get("FENRIR_DASH_SINCE") or "").strip()


def _floor_ms(value: str) -> float | None:
    """Parse a floor/timestamp value to an epoch (ms) in a host-tz-independent way: a bare date
    (`2026-06-29`) → that day's 00:00 **UTC**; a `T` value with no offset → UTC (not local), so a
    naive datetime never silently picks up the host's timezone. None if unparseable."""
    if "T" not in value:
        value = f"{value}T00:00:00+00:00"
    elif not (value.endswith("Z") or "+" in value[10:] or "-" in value[10:]):
        value = f"{value}+00:00"  # naive -> treat as UTC
    return _iso_ms(value)


def _before_floor(ts: str, since: str) -> bool:
    """True if event timestamp `ts` falls strictly before the floor `since` (so it is dropped).

    Compares on the epoch (tz-correct across mixed offsets/`Z`) — a plain lexicographic compare is
    only safe for same-offset strings. If either side can't be parsed, fall back to a string
    compare. A tie (equal instant) is KEPT (not before the floor)."""
    if not ts or not since:
        return False
    a, b = _floor_ms(ts), _floor_ms(since)
    if a is None or b is None:
        return ts < since  # best-effort string fallback
    return a < b


def encode_project(path: Path) -> str:
    """Claude Code encodes a project dir as its absolute path with the separators replaced by `-`.

    On POSIX that means `/` and `.`; on Windows the drive colon and backslashes too, and the
    drive letter is lowercased (Claude's convention), so `C:\\Users\\me\\repo` -> `c--Users-me-repo`,
    matching the real `~/.claude/projects/<slug>` dir. On a POSIX host the output is byte-identical
    to the historical `/` `.` -> `-` (no drive/backslash/colon to touch); without the Windows
    separators and the lowercase drive the slug never matches and telemetry can't scope to the repo.

    The drive is lowercased to a CANONICAL form; `current_project_slug` matches case-insensitively
    so a project dir created with either drive casing still resolves."""
    resolved = path.resolve()
    s = str(resolved)
    drive = resolved.drive  # e.g. "C:" on Windows, "" on POSIX
    if drive and s[: len(drive)] == drive:
        s = drive.lower() + s[len(drive) :]
    return s.replace("\\", "-").replace("/", "-").replace(":", "-").replace(".", "-")


def list_projects(claude_dir: Path) -> list[str]:
    base = claude_dir / "projects"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


@lru_cache(maxsize=64)
def _git_root(cwd: Path) -> Path | None:
    """The git repo root containing `cwd`, or None. So a subdir (e.g. dashboard/) maps to the
    repo, not to a phantom project created by an accidental subdir invocation. Cached — a server
    process's cwd is constant, so this must not fork `git` on every HTTP request."""
    try:
        r = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except Exception:
        pass
    return None


def resolution_base(cwd: Path | None = None) -> Path:
    """The directory project/board resolution should key off when no explicit `cwd` is given.

    Order: an explicit `cwd` arg (tests pass one) > the **in-session repo root**
    `CLAUDE_PROJECT_DIR` env (set+non-empty) > the real `Path.cwd()`. The env branch is what
    lets the bundled-backend launcher (which must run with cwd=<plugin>/dashboard so
    `backend.app` imports) still resolve the USER's repo: the launcher exports
    CLAUDE_PROJECT_DIR=<user repo>, and reader+writer then agree on the same project. Gated on
    the var being non-empty so run-from-repo dev mode (and the cwd-based tests) are unchanged
    when it is absent."""
    if cwd is not None:
        return cwd
    env = (os.environ.get("CLAUDE_PROJECT_DIR") or "").strip()
    return Path(env) if env else Path.cwd()


def current_project_slug(claude_dir: Path, cwd: Path | None = None) -> str | None:
    """Best-match the project for `cwd` (default: `CLAUDE_PROJECT_DIR` if set, else the real cwd —
    see `resolution_base`). When the base is inside a git repo it resolves to the **repo root**
    first, so running from a subdir (e.g. `dashboard/`) maps to the repo's project rather than a
    phantom `<repo>-dashboard` project an accidental subdir invocation may have created in
    ~/.claude/projects (that bug once mis-resolved the board). Then picks the longest available
    slug that prefixes the (root-resolved) encoding. NOTE: only holds when `git` is available;
    otherwise it falls back to longest-prefix on the raw base. If you genuinely run a subdir AS its
    own project, pin it with the `project=` param / the `FENRIR_DASH_BOARD` env. None if nothing
    matches."""
    base = resolution_base(cwd)
    root = _git_root(base) or base
    enc = encode_project(root).lower()
    # Match case-INSENSITIVELY (a machine can hold both `C--…` and `c--…` project dirs depending on
    # the drive casing Claude saw); return the REAL dir name `p` so find_transcripts scans it.
    candidates = [p for p in list_projects(claude_dir) if enc == p.lower() or enc.startswith(p.lower())]
    return max(candidates, key=len) if candidates else None


def find_transcripts(claude_dir: Path, project: str | None = None) -> list[Path]:
    """All *.jsonl transcripts (main sessions + session subdirs + workflow agents).

    `project` filters to one projects/<project> dir; None scans every project.
    """
    base = claude_dir / "projects"
    if not base.is_dir():
        return []
    root = base / project if project else base
    if not root.exists():
        return []
    return sorted(root.rglob("*.jsonl"))


def _event(obj: dict) -> dict | None:
    if not isinstance(obj, dict):
        return None
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return None
    usage = msg.get("usage")
    model = msg.get("model")
    if not isinstance(usage, dict) or not model:
        return None
    ts = obj.get("timestamp", "") or ""
    return {
        "ts": ts,
        "day": ts[:10],
        "model": model,
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "cache_creation": int(usage.get("cache_creation_input_tokens", 0) or 0),
        "cache_read": int(usage.get("cache_read_input_tokens", 0) or 0),
        "cost": pricing.cost_of(usage, model),
        "session_id": obj.get("sessionId", "") or "",
        "skill": obj.get("attributionSkill") or "",
        "plugin": obj.get("attributionPlugin") or "",
        "source": "subagent" if obj.get("isSidechain") else "main",
    }


def load_events(claude_dir: Path, project: str | None = None) -> list[dict]:
    since = _since()
    events: list[dict] = []
    for path in find_transcripts(claude_dir, project):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            ev = _event(obj)
            if not ev:
                continue
            if since and _before_floor(ev["ts"], since):  # consumption floor
                continue
            events.append(ev)
    return events


# --- aggregations (pure over an event list) -------------------------------------------


def _tok(e: dict) -> int:
    return e["input_tokens"] + e["output_tokens"] + e["cache_creation"] + e["cache_read"]


def summary(events: list[dict]) -> dict:
    days = sorted({e["day"] for e in events if e["day"]})
    total_cost = sum(e["cost"] for e in events)
    # Cost split by component so "is cache what costs me?" is answerable. input/output/cache-read
    # are exact; cache-write is the remainder (absorbs the 5m-vs-1h TTL split the flat event loses),
    # so the four always reconcile to total_cost.
    ci = co = crd = 0.0
    for e in events:
        r = pricing.rates_for(e["model"])
        ci += e["input_tokens"] * r["input"] / 1_000_000.0
        co += e["output_tokens"] * r["output"] / 1_000_000.0
        crd += e["cache_read"] * r["read"] / 1_000_000.0
    return {
        "calls": len(events),
        "input_tokens": sum(e["input_tokens"] for e in events),
        "output_tokens": sum(e["output_tokens"] for e in events),
        "cache_write_tokens": sum(e["cache_creation"] for e in events),
        "cache_read_tokens": sum(e["cache_read"] for e in events),
        "cache_tokens": sum(e["cache_creation"] + e["cache_read"] for e in events),
        "total_tokens": sum(_tok(e) for e in events),
        "cost_usd": round(total_cost, 4),
        "cost_breakdown": {
            "input": round(ci, 4), "output": round(co, 4),
            "cache_read": round(crd, 4), "cache_write": round(total_cost - ci - co - crd, 4),
        },
        "models": sorted({e["model"] for e in events}),
        "sessions": len({e["session_id"] for e in events if e["session_id"]}),
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
    }


def _group(events: Iterable[dict], key: str, label_default: str = "(none)") -> list[dict]:
    agg: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                 "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0}
    )
    for e in events:
        k = e.get(key) or label_default
        a = agg[k]
        a["calls"] += 1
        a["input_tokens"] += e["input_tokens"]
        a["output_tokens"] += e["output_tokens"]
        a["cache_write_tokens"] += e["cache_creation"]
        a["cache_read_tokens"] += e["cache_read"]
        a["cost_usd"] += e["cost"]
    out = [{"key": k, **v, "cost_usd": round(v["cost_usd"], 4)} for k, v in agg.items()]
    return sorted(out, key=lambda r: r["cost_usd"], reverse=True)


def by_model(events: list[dict]) -> list[dict]:
    return _group(events, "model")


def by_skill(events: list[dict]) -> list[dict]:
    return _group(events, "skill")


def by_source(events: list[dict]) -> list[dict]:
    return _group(events, "source")


def by_day(events: list[dict]) -> list[dict]:
    agg: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "cost_usd": 0.0})
    for e in events:
        if not e["day"]:
            continue
        agg[e["day"]]["tokens"] += _tok(e)
        agg[e["day"]]["cost_usd"] += e["cost"]
    return [
        {"day": d, "tokens": v["tokens"], "cost_usd": round(v["cost_usd"], 4)}
        for d, v in sorted(agg.items())
    ]


def agents(events: list[dict]) -> dict:
    """A 'who spent what' view: split by source (main vs subagent) then by skill."""
    return {
        "by_source": by_source(events),
        "by_skill": by_skill(events),
    }


def efficiency(events: list[dict]) -> dict:
    """How hard prompt-caching is working, and what it saves — per model + total.

    `uncached_cost` charges EVERY input-side token (fresh + cache read + cache write) at the
    full input rate (what it would cost with no caching); `actual_cost` is the real,
    cache-discounted cost. `savings` = uncached − actual (caching is the efficient path, not
    waste). `cache_hit_ratio` = cache_read / (fresh_input + cache_read): the share of input
    served cheap from cache — a LOW ratio with high spend is the real waste to target."""
    per: dict[str, dict] = defaultdict(
        lambda: {"fresh_input": 0, "cache_read": 0, "cache_write": 0, "output": 0,
                 "actual_cost": 0.0, "input_rate": 0.0, "output_rate": 0.0, "calls": 0})
    for e in events:
        r = pricing.rates_for(e["model"])
        d = per[e["model"]]
        d["fresh_input"] += e["input_tokens"]; d["cache_read"] += e["cache_read"]
        d["cache_write"] += e["cache_creation"]; d["output"] += e["output_tokens"]
        d["actual_cost"] += e["cost"]; d["calls"] += 1
        d["input_rate"] = r["input"]; d["output_rate"] = r["output"]

    def row(model: str, d: dict) -> dict:
        uncached = ((d["fresh_input"] + d["cache_read"] + d["cache_write"]) * d["input_rate"]
                    + d["output"] * d["output_rate"]) / 1_000_000.0
        cin = d["fresh_input"] + d["cache_read"]
        return {
            "model": model, "fresh_input_tokens": d["fresh_input"],
            "cache_read_tokens": d["cache_read"], "cache_write_tokens": d["cache_write"],
            "output_tokens": d["output"], "actual_cost": round(d["actual_cost"], 4),
            "uncached_cost": round(uncached, 4),
            "savings": round(uncached - d["actual_cost"], 4),
            "cache_hit_ratio": round(d["cache_read"] / cin, 4) if cin else 0.0,
            # Cache-read is the cached PREFIX (system + tool schemas + history) re-read on EVERY
            # call at 0.1× — a big number is "context size × calls", not a leak. The per-call
            # average makes that legible: it ≈ the live context, not something growing unbounded.
            "calls": d["calls"],
            "cache_read_per_call": round(d["cache_read"] / d["calls"]) if d["calls"] else 0,
        }

    rows = sorted((row(m, d) for m, d in per.items()),
                  key=lambda x: x["actual_cost"], reverse=True)
    ta = sum(r["actual_cost"] for r in rows)
    tu = sum(r["uncached_cost"] for r in rows)
    tfi = sum(r["fresh_input_tokens"] for r in rows)
    tcr = sum(r["cache_read_tokens"] for r in rows)
    tcalls = sum(r["calls"] for r in rows)
    return {
        "by_model": rows,
        "total": {
            "actual_cost": round(ta, 4), "uncached_cost": round(tu, 4),
            "savings": round(tu - ta, 4),
            "cache_hit_ratio": round(tcr / (tfi + tcr), 4) if (tfi + tcr) else 0.0,
            "fresh_input_tokens": tfi, "cache_read_tokens": tcr,
            "calls": tcalls,
            "cache_read_per_call": round(tcr / tcalls) if tcalls else 0,
        },
    }


# --- subagent attribution (who/what/when/how-much) ------------------------------------
# Layout: <session>/subagents/agent-<id>.meta.json {agentType, description, toolUseId}
# is co-located with agent-<id>.jsonl (the run's transcript). Tokens come ONLY from the
# .jsonl (already part of the sidechain stream) — meta is identity only, so there is no
# double counting. Runs reconcile against the by_source subagent total.


def _iso_ms(ts: str) -> float | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
    except (ValueError, AttributeError):
        return None


def _run_tokens(path: Path) -> dict:
    """Sum a subagent transcript's own usage events (single source of truth for tokens)."""
    inp = out = cw = cr = 0
    cost = 0.0
    first = last = ""
    if not path.exists():
        return {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0,
                "cache_read_tokens": 0, "cost_usd": 0.0, "model": "",
                "when": "", "duration_ms": 0, "session_id": "", "found": False}
    model = session = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        ev = _event(obj)
        if not ev:
            continue
        inp += ev["input_tokens"]
        out += ev["output_tokens"]
        cw += ev["cache_creation"]
        cr += ev["cache_read"]
        cost += ev["cost"]
        model = model or ev["model"]
        session = session or ev["session_id"]
        ts = ev["ts"]
        if ts:
            first = first or ts
            last = ts
    dur = 0
    a, b = _iso_ms(first), _iso_ms(last)
    if a is not None and b is not None:
        dur = int(b - a)
    return {"input_tokens": inp, "output_tokens": out, "cache_write_tokens": cw,
            "cache_read_tokens": cr, "cost_usd": round(cost, 4),
            "model": model, "when": first, "duration_ms": dur, "session_id": session,
            "found": True}


def subagent_runs(claude_dir: Path, project: str | None = None) -> dict:
    """One record per subagent run: identity from agent-*.meta.json, tokens from the
    co-located agent-*.jsonl. Reconciles: attributed + unattributed == subagent total."""
    since = _since()
    base = claude_dir / "projects"
    root = (base / project) if project else base
    runs: list[dict] = []
    if root.exists():
        for meta_path in sorted(root.rglob("agent-*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict):
                continue
            tok = _run_tokens(meta_path.with_suffix("").with_suffix(".jsonl"))
            if since and _before_floor(tok["when"], since):  # consumption floor
                continue
            runs.append({
                "run_id": meta_path.name.replace(".meta.json", ""),  # stable: "agent-<id>"
                "agent_type": meta.get("agentType", "?"),
                "description": meta.get("description", ""),
                "tool_use_id": meta.get("toolUseId", ""),
                "session_id": tok["session_id"],
                "when": tok["when"],
                "model": tok["model"],
                "status": "completed" if tok["found"] else "no-transcript",
                "duration_ms": tok["duration_ms"],
                "input_tokens": tok["input_tokens"],
                "output_tokens": tok["output_tokens"],
                "cache_write_tokens": tok["cache_write_tokens"],
                "cache_read_tokens": tok["cache_read_tokens"],
                "total_tokens": tok["input_tokens"] + tok["output_tokens"],
                "cost_usd": tok["cost_usd"],
                "attributed": tok["found"] and (tok["input_tokens"] + tok["output_tokens"]) > 0,
            })
    runs.sort(key=lambda r: r["when"], reverse=True)

    # Reconcile against the authoritative subagent total (same event stream).
    sub_events = [e for e in load_events(claude_dir, project) if e["source"] == "subagent"]
    sub_total = sum(e["input_tokens"] + e["output_tokens"] for e in sub_events)
    attributed = sum(r["input_tokens"] + r["output_tokens"] for r in runs)

    agg: dict[str, dict] = defaultdict(
        lambda: {"runs": 0, "input_tokens": 0, "output_tokens": 0,
                 "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0}
    )
    for r in runs:
        a = agg[r["agent_type"]]
        a["runs"] += 1
        a["input_tokens"] += r["input_tokens"]
        a["output_tokens"] += r["output_tokens"]
        a["cache_write_tokens"] += r["cache_write_tokens"]
        a["cache_read_tokens"] += r["cache_read_tokens"]
        a["cost_usd"] += r["cost_usd"]
    by_type = sorted(
        ({"agent_type": k, **v, "cost_usd": round(v["cost_usd"], 4)} for k, v in agg.items()),
        key=lambda r: r["cost_usd"], reverse=True,
    )
    return {
        "runs": runs,
        "by_type": by_type,
        "subagent_total_tokens": sub_total,
        "attributed_tokens": attributed,
        "unattributed_tokens": max(0, sub_total - attributed),
    }
