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
from pathlib import Path

from . import pricing


def default_claude_dir() -> Path:
    return Path.home() / ".claude"


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
