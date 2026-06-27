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
from datetime import UTC, datetime

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
    _emit(s.set_status(a.kind, a.id, Status(a.status)))


def _cmd_assign(s: BoardStore, a) -> None:
    _emit(s.assign(a.kind, a.id, a.agent))


def _cmd_log(s: BoardStore, a) -> None:
    entry = WorkLogEntry(agent=a.agent, session_id=a.session, input_tokens=a.in_tokens,
                         output_tokens=a.out_tokens, cost_usd=a.cost, note=a.note,
                         at=a.at or datetime.now(UTC).isoformat())
    _emit(s.log_work(a.kind, a.id, entry))


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

    a = sub.add_parser("delete"); a.add_argument("--kind", required=True)
    a.add_argument("--id", required=True); a.set_defaults(fn=_cmd_delete)

    sub.add_parser("list").set_defaults(fn=_cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.fn(BoardStore(), args)
    except (KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
