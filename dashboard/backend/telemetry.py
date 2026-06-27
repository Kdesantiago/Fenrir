"""Parse real Claude Code telemetry from ~/.claude transcripts.

Each assistant message line carries `message.model`, `message.usage`
(input/output/cache tokens), a `timestamp`, `sessionId`, `isSidechain` (subagent vs
main thread), and `attributionSkill`/`attributionPlugin` (which Fenrir skill spent the
tokens). We normalize those into events and aggregate by model / skill / day / source /
session — deriving USD cost from the price book. Read-only; never mutates the logs.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from . import pricing


def default_claude_dir() -> Path:
    return Path.home() / ".claude"


def encode_project(path: Path) -> str:
    """Claude Code encodes a project dir as its absolute path with `/` and `.` -> `-`."""
    return str(path.resolve()).replace("/", "-").replace(".", "-")


def list_projects(claude_dir: Path) -> list[str]:
    base = claude_dir / "projects"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def current_project_slug(claude_dir: Path, cwd: Path | None = None) -> str | None:
    """Best-match the project for `cwd` (default: real cwd). Picks the longest available
    project slug that prefixes the cwd encoding, so running from a subdir (e.g. dashboard/)
    still resolves to the repo's project. None if nothing matches."""
    enc = encode_project(cwd or Path.cwd())
    candidates = [p for p in list_projects(claude_dir) if enc == p or enc.startswith(p)]
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
    events: list[dict] = []
    for path in find_transcripts(claude_dir, project):
        try:
            text = path.read_text()
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
            if ev:
                events.append(ev)
    return events


# --- aggregations (pure over an event list) -------------------------------------------


def _tok(e: dict) -> int:
    return e["input_tokens"] + e["output_tokens"] + e["cache_creation"] + e["cache_read"]


def summary(events: list[dict]) -> dict:
    days = sorted({e["day"] for e in events if e["day"]})
    return {
        "calls": len(events),
        "input_tokens": sum(e["input_tokens"] for e in events),
        "output_tokens": sum(e["output_tokens"] for e in events),
        "cache_tokens": sum(e["cache_creation"] + e["cache_read"] for e in events),
        "total_tokens": sum(_tok(e) for e in events),
        "cost_usd": round(sum(e["cost"] for e in events), 4),
        "models": sorted({e["model"] for e in events}),
        "sessions": len({e["session_id"] for e in events if e["session_id"]}),
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
    }


def _group(events: Iterable[dict], key: str, label_default: str = "(none)") -> list[dict]:
    agg: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    )
    for e in events:
        k = e.get(key) or label_default
        a = agg[k]
        a["calls"] += 1
        a["input_tokens"] += e["input_tokens"]
        a["output_tokens"] += e["output_tokens"]
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
    inp = out = 0
    cost = 0.0
    first = last = ""
    if not path.exists():
        return {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "model": "",
                "when": "", "duration_ms": 0, "session_id": "", "found": False}
    model = session = ""
    for line in path.read_text().splitlines():
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
    return {"input_tokens": inp, "output_tokens": out, "cost_usd": round(cost, 4),
            "model": model, "when": first, "duration_ms": dur, "session_id": session,
            "found": True}


def subagent_runs(claude_dir: Path, project: str | None = None) -> dict:
    """One record per subagent run: identity from agent-*.meta.json, tokens from the
    co-located agent-*.jsonl. Reconciles: attributed + unattributed == subagent total."""
    base = claude_dir / "projects"
    root = (base / project) if project else base
    runs: list[dict] = []
    if root.exists():
        for meta_path in sorted(root.rglob("agent-*.meta.json")):
            try:
                meta = json.loads(meta_path.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(meta, dict):
                continue
            tok = _run_tokens(meta_path.with_suffix("").with_suffix(".jsonl"))
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
        lambda: {"runs": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    )
    for r in runs:
        a = agg[r["agent_type"]]
        a["runs"] += 1
        a["input_tokens"] += r["input_tokens"]
        a["output_tokens"] += r["output_tokens"]
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
