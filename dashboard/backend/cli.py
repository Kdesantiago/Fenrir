"""Board CLI — how AGENTS drive the Agile board (via Bash), same store as the web API.

Examples (run from dashboard/):
  python -m backend.cli epic add --title "Monitoring dashboard"
  python -m backend.cli feature add --epic epic-1 --title "Telemetry view"
  python -m backend.cli story add --feature feat-1 --title "Cost by model" --assignee architect \
      --as-a "tech lead" --i-want "cost per model" --so-that "I can budget"
  python -m backend.cli move --kind story --id us-1 --status in_progress
  python -m backend.cli assign --kind story --id us-1 --agent coder
  python -m backend.cli log --kind story --id us-1 --agent coder --in-tokens 1200 --out-tokens 800 --cost 0.05
  python -m backend.cli list
Each mutating command prints the resulting object as JSON so an agent can parse it.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime

from . import config, telemetry
from .board import BoardStore
from .models import Status, WorkLogEntry


def _emit(obj) -> None:
    print(json.dumps(obj.model_dump() if hasattr(obj, "model_dump") else obj, indent=2))


def _cmd_epic(s: BoardStore, a) -> None:
    _emit(s.add_epic(a.title, a.description, a.color, datetime.now(UTC).isoformat()))


def _cmd_feature(s: BoardStore, a) -> None:
    _emit(s.add_feature(a.epic, a.title, a.description))


def _cmd_story(s: BoardStore, a) -> None:
    _emit(s.add_story(a.feature, a.title, a.assignee, a.points, a.as_a, a.i_want,
                      a.so_that, a.ac or []))


def _cmd_task(s: BoardStore, a) -> None:
    _emit(s.add_task(a.story, a.title, a.assignee))


def _cmd_move(s: BoardStore, a) -> None:
    _emit(s.set_status(a.kind, a.id, Status(a.status), at=datetime.now(UTC).isoformat()))


def _cmd_metrics(s: BoardStore, a) -> None:
    _emit(s.flow_metrics(now=datetime.now(UTC).isoformat()))


def _cmd_assign(s: BoardStore, a) -> None:
    _emit(s.assign(a.kind, a.id, a.agent))


def _cmd_log(s: BoardStore, a) -> None:
    entry = WorkLogEntry(agent=a.agent, session_id=a.session, input_tokens=a.in_tokens,
                         output_tokens=a.out_tokens, cost_usd=a.cost, note=a.note,
                         at=a.at or datetime.now(UTC).isoformat())
    _emit(s.log_work(a.kind, a.id, entry))


def _cmd_link(s: BoardStore, a) -> None:
    """Pull REAL telemetry (by session and/or skill) into a story/task work_log.
    Idempotent per (session, item); writes one entry per source (main vs subagent)."""
    if a.session and s.has_session_for(a.kind, a.id, a.session):
        if getattr(a, "refresh", False):
            s.clear_session_links(a.kind, a.id, a.session)  # re-link with current totals
        else:
            print(json.dumps({"skipped": f"session {a.session} already linked to {a.id}"}))
            return
    if a.session:  # exclusivity: don't lump a session that already has per-run attributions
        runs = [e for e in s.entries_for_session(a.session) if e["source"] == "telemetry-run"]
        if runs:
            raise ValueError(
                f"session {a.session} already has per-run attributions (e.g. {runs[0]['id']}); "
                "use `attribute` per run, not whole-session `link`, for this session")
    cd = config.claude_dir()
    project = a.project or telemetry.current_project_slug(cd)  # default: current repo
    ev = telemetry.load_events(cd, project)
    ev = [e for e in ev
          if (not a.session or e["session_id"] == a.session)
          and (not a.skill or e["skill"] == a.skill)]
    if not ev:
        raise ValueError("no telemetry matched the given --session/--skill/--project")
    groups: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0, "cost": 0.0, "n": 0})
    for e in ev:
        g = groups[e["source"]]
        g["in"] += e["input_tokens"]; g["out"] += e["output_tokens"]
        g["cost"] += e["cost"]; g["n"] += 1
    now = datetime.now(UTC).isoformat()
    for src, g in sorted(groups.items()):
        s.log_work(a.kind, a.id, WorkLogEntry(
            agent=a.agent or src, subagent_type=(src if src == "subagent" else ""),
            session_id=a.session, source="telemetry-link",
            input_tokens=g["in"], output_tokens=g["out"], cost_usd=round(g["cost"], 4),
            note=a.note or f"linked {g['n']} {src} events", at=now))
    _emit(s.load())


def _cmd_attribute(s: BoardStore, a) -> None:
    """Attach ONE subagent run's REAL tokens/cost to a US (distinct per run, no lump)."""
    cd = config.claude_dir()
    project = a.project or telemetry.current_project_slug(cd)
    runs = telemetry.subagent_runs(cd, project)["runs"]
    run = next((r for r in runs if r["run_id"] == a.run), None)
    if not run:
        raise ValueError(f"no subagent run '{a.run}' (use a run_id from the Subagents view / "
                         "/api/telemetry/subagents)")
    if s.has_run_for(a.kind, a.id, a.run):
        print(json.dumps({"skipped": f"run {a.run} already attributed to {a.id}"}))
        return
    sess = run["session_id"]
    linked = [e for e in s.entries_for_session(sess) if e["source"] == "telemetry-link"]
    if linked:
        raise ValueError(f"session {sess} is already whole-session linked to {linked[0]['id']}; "
                         "`link` and `attribute` are mutually exclusive for one session")
    entry = WorkLogEntry(
        agent=a.agent or run["agent_type"], subagent_type=run["agent_type"],
        session_id=sess, run_id=a.run, source="telemetry-run",
        input_tokens=run["input_tokens"], output_tokens=run["output_tokens"],
        cost_usd=run["cost_usd"], note=a.note or (run["description"] or "")[:80],
        at=datetime.now(UTC).isoformat())
    _emit(s.log_work(a.kind, a.id, entry))


def _cmd_trace(s: BoardStore, a) -> None:
    rows = s.trace(a.us or None)
    total = round(sum(r.get("cost_usd", 0) for r in rows), 4)
    tin = sum(r.get("input_tokens", 0) for r in rows)
    tout = sum(r.get("output_tokens", 0) for r in rows)
    for r in rows:
        print(f"{r.get('at',''):26} {r['us_id']:7} {r.get('agent',''):14} "
              f"in={r.get('input_tokens',0):>8} out={r.get('output_tokens',0):>7} "
              f"${r.get('cost_usd',0):.4f}  [{r.get('source','')}] {r.get('title','')}")
    print(f"--- {len(rows)} entries | in={tin} out={tout} | total ${total:.4f}")


def _cmd_delete(s: BoardStore, a) -> None:
    s.delete(a.kind, a.id)
    print(json.dumps({"deleted": a.id}))


def _cmd_list(s: BoardStore, a) -> None:
    b = s.load()
    for e in b.epics:
        print(f"[EPIC {e.id}] {e.title}  <{e.status.value}>")
        for f in [f for f in b.features if f.epic_id == e.id]:
            print(f"  [FEAT {f.id}] {f.title}  <{f.status.value}>")
            for st in [s2 for s2 in b.stories if s2.feature_id == f.id]:
                who = f" @{st.assignee}" if st.assignee else ""
                print(f"    [US {st.id}] {st.title}  <{st.status.value}>{who}  ({st.points}pt)")
                for t in [t for t in b.tasks if t.story_id == st.id]:
                    tw = f" @{t.assignee}" if t.assignee else ""
                    print(f"      [TASK {t.id}] {t.title}  <{t.status.value}>{tw}")
    if not b.epics:
        print("(empty board)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backend.cli", description="Fenrir board CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("epic").add_subparsers(dest="op", required=True)
    a = pe.add_parser("add"); a.add_argument("--title", required=True)
    a.add_argument("--description", default=""); a.add_argument("--color", default="#6366f1")
    a.set_defaults(fn=_cmd_epic)

    pf = sub.add_parser("feature").add_subparsers(dest="op", required=True)
    a = pf.add_parser("add"); a.add_argument("--epic", required=True)
    a.add_argument("--title", required=True); a.add_argument("--description", default="")
    a.set_defaults(fn=_cmd_feature)

    ps = sub.add_parser("story").add_subparsers(dest="op", required=True)
    a = ps.add_parser("add"); a.add_argument("--feature", required=True)
    a.add_argument("--title", required=True); a.add_argument("--assignee", default="")
    a.add_argument("--points", type=int, default=0); a.add_argument("--as-a", dest="as_a", default="")
    a.add_argument("--i-want", dest="i_want", default=""); a.add_argument("--so-that", dest="so_that", default="")
    a.add_argument("--ac", action="append", help="acceptance criterion (repeatable)")
    a.set_defaults(fn=_cmd_story)

    pt = sub.add_parser("task").add_subparsers(dest="op", required=True)
    a = pt.add_parser("add"); a.add_argument("--story", required=True)
    a.add_argument("--title", required=True); a.add_argument("--assignee", default="")
    a.set_defaults(fn=_cmd_task)

    a = sub.add_parser("move"); a.add_argument("--kind", required=True)
    a.add_argument("--id", required=True)
    a.add_argument("--status", required=True, choices=[s.value for s in Status])
    a.set_defaults(fn=_cmd_move)

    a = sub.add_parser("assign"); a.add_argument("--kind", required=True)
    a.add_argument("--id", required=True); a.add_argument("--agent", required=True)
    a.set_defaults(fn=_cmd_assign)

    a = sub.add_parser("log"); a.add_argument("--kind", required=True)
    a.add_argument("--id", required=True); a.add_argument("--agent", default="")
    a.add_argument("--session", default=""); a.add_argument("--in-tokens", dest="in_tokens", type=int, default=0)
    a.add_argument("--out-tokens", dest="out_tokens", type=int, default=0)
    a.add_argument("--cost", type=float, default=0.0); a.add_argument("--note", default="")
    a.add_argument("--at", default=""); a.set_defaults(fn=_cmd_log)

    a = sub.add_parser("link", help="pull real telemetry (by session/skill) into a work_log")
    a.add_argument("--kind", required=True); a.add_argument("--id", required=True)
    a.add_argument("--session", default=""); a.add_argument("--skill", default="")
    a.add_argument("--project", default=None); a.add_argument("--agent", default="")
    a.add_argument("--note", default="")
    a.add_argument("--refresh", action="store_true",
                   help="re-link with current totals (drop+rewrite prior session link entries)")
    a.set_defaults(fn=_cmd_link)

    a = sub.add_parser("delete"); a.add_argument("--kind", required=True)
    a.add_argument("--id", required=True); a.set_defaults(fn=_cmd_delete)

    a = sub.add_parser("attribute", help="attach ONE subagent run's real cost to a US (per-run)")
    a.add_argument("--kind", required=True); a.add_argument("--id", required=True)
    a.add_argument("--run", required=True, help="run_id (agent-<id>) from the Subagents view")
    a.add_argument("--project", default=None); a.add_argument("--agent", default="")
    a.add_argument("--note", default=""); a.set_defaults(fn=_cmd_attribute)

    a = sub.add_parser("trace", help="print the cost trace (flattened work_log), chronological")
    a.add_argument("--us", default="", help="filter to one story id"); a.set_defaults(fn=_cmd_trace)

    sub.add_parser("metrics", help="flow metrics: cycle time, throughput, WIP, forecast").set_defaults(fn=_cmd_metrics)

    sub.add_parser("list").set_defaults(fn=_cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.fn(config.store(), args)
    except (KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
