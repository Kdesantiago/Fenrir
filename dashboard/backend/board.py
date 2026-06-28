"""Agile board store — Epic → Feature → User Story → Task over a git-tracked JSON file.

LifeOS spirit: the board is plain, reviewable, version-controlled data (`data/board.json`),
not a hidden DB. Both the web API and the CLI (which the agents drive) go through this one
module, so there is a single source of truth.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .models import Board, Epic, Feature, Status, Task, Transition, UserStory, WorkLogEntry

DEFAULT_BOARD_PATH = Path(__file__).resolve().parent.parent / "data" / "board.json"

_PREFIX = {"epic": "epic", "feature": "feat", "story": "us", "task": "task"}


class BoardStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_BOARD_PATH

    # --- persistence -------------------------------------------------------------------
    def load(self) -> Board:
        if not self.path.exists():
            return Board()
        try:
            return Board.model_validate_json(self.path.read_text())
        except Exception:
            return Board()

    def save(self, board: Board) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(board.model_dump_json(indent=2) + "\n")

    # --- id generation (collision-safe: max numeric suffix + 1) ------------------------
    def _next_id(self, kind: str, existing: list[str]) -> str:
        prefix = _PREFIX[kind]
        n = 0
        for i in existing:
            if i.startswith(prefix + "-"):
                try:
                    n = max(n, int(i.rsplit("-", 1)[1]))
                except ValueError:
                    pass
        return f"{prefix}-{n + 1}"

    # --- create ------------------------------------------------------------------------
    def add_epic(self, title: str, description: str = "", color: str = "#6366f1",
                 created: str = "") -> Epic:
        b = self.load()
        epic = Epic(id=self._next_id("epic", [e.id for e in b.epics]), title=title,
                    description=description, color=color, created=created)
        b.epics.append(epic)
        self.save(b)
        return epic

    def add_feature(self, epic_id: str, title: str, description: str = "") -> Feature:
        b = self.load()
        if not any(e.id == epic_id for e in b.epics):
            raise KeyError(f"epic {epic_id} not found")
        feat = Feature(id=self._next_id("feature", [f.id for f in b.features]),
                       epic_id=epic_id, title=title, description=description)
        b.features.append(feat)
        self.save(b)
        return feat

    def add_story(self, feature_id: str, title: str, assignee: str = "", points: int = 0,
                  as_a: str = "", i_want: str = "", so_that: str = "",
                  acceptance_criteria: list[str] | None = None) -> UserStory:
        b = self.load()
        if not any(f.id == feature_id for f in b.features):
            raise KeyError(f"feature {feature_id} not found")
        story = UserStory(
            id=self._next_id("story", [s.id for s in b.stories]), feature_id=feature_id,
            title=title, assignee=assignee, points=points, as_a=as_a, i_want=i_want,
            so_that=so_that, acceptance_criteria=acceptance_criteria or [],
        )
        b.stories.append(story)
        self.save(b)
        return story

    def add_task(self, story_id: str, title: str, assignee: str = "") -> Task:
        b = self.load()
        if not any(s.id == story_id for s in b.stories):
            raise KeyError(f"story {story_id} not found")
        task = Task(id=self._next_id("task", [t.id for t in b.tasks]), story_id=story_id,
                    title=title, assignee=assignee)
        b.tasks.append(task)
        self.save(b)
        return task

    # --- mutate ------------------------------------------------------------------------
    def _collection(self, b: Board, kind: str) -> list[Any]:
        coll: dict[str, list[Any]] = {"epic": b.epics, "feature": b.features,
                                      "story": b.stories, "task": b.tasks}
        return coll[kind]

    def _find(self, b: Board, kind: str, item_id: str) -> Any:
        for item in self._collection(b, kind):
            if item.id == item_id:
                return item
        raise KeyError(f"{kind} {item_id} not found")

    def set_status(self, kind: str, item_id: str, status: Status, at: str = "") -> Any:
        b = self.load()
        item = self._find(b, kind, item_id)
        prev = item.status
        if prev != status:  # only real moves are logged (basis for cycle time / WIP age)
            item.transitions.append(Transition(from_status=str(prev), to_status=str(status), at=at))
        item.status = status
        self.save(b)
        return item

    def assign(self, kind: str, item_id: str, assignee: str) -> Any:
        if kind not in ("story", "task"):
            raise ValueError("only stories and tasks take an assignee")
        b = self.load()
        item = self._find(b, kind, item_id)
        item.assignee = assignee
        self.save(b)
        return item

    def log_work(self, kind: str, item_id: str, entry: WorkLogEntry) -> Any:
        if kind not in ("story", "task"):
            raise ValueError("work can only be logged on stories and tasks")
        b = self.load()
        item = self._find(b, kind, item_id)
        item.work_log.append(entry)
        self.save(b)
        return item

    def clear_session_links(self, kind: str, item_id: str, session_id: str) -> int:
        """Drop this item's whole-session `link` entries for a session, so a refresh can
        re-link with up-to-date totals (continuous cost logging). Leaves per-run `attribute`
        entries and manual entries untouched. Returns how many were removed."""
        if kind not in ("story", "task") or not session_id:
            return 0
        b = self.load()
        item = self._find(b, kind, item_id)
        before = len(item.work_log)
        item.work_log = [w for w in item.work_log
                         if not (w.session_id == session_id and w.source == "telemetry-link")]
        removed = before - len(item.work_log)
        if removed:
            self.save(b)
        return removed

    # --- cost rollups + trace (derived from work_log — the single source) --------------
    def has_session_for(self, kind: str, item_id: str, session_id: str) -> bool:
        """True if a work_log entry for this item already covers session_id (idempotency)."""
        b = self.load()
        item = self._find(b, kind, item_id)
        return any(w.session_id == session_id and session_id for w in item.work_log)

    def has_run_for(self, kind: str, item_id: str, run_id: str) -> bool:
        """True if this item already has the given subagent run attributed (idempotency)."""
        b = self.load()
        item = self._find(b, kind, item_id)
        return any(w.run_id == run_id and run_id for w in item.work_log)

    def entries_for_session(self, session_id: str) -> list[dict]:
        """Board-wide: every work_log entry (across all stories+tasks) for a session_id.
        Used to keep `link` (whole-session) and `attribute` (per-run) mutually exclusive so
        the same spend is never counted twice. Blind to session_id=='' manual entries."""
        if not session_id:
            return []
        b = self.load()
        out: list[dict] = []
        for kind, items in (("story", b.stories), ("task", b.tasks)):
            for it in items:
                for w in it.work_log:
                    if w.session_id == session_id:
                        out.append({"kind": kind, "id": it.id, "source": w.source})
        return out

    def costs(self) -> dict:
        """Per Epic/Feature/US cost rollup from work_log (tasks roll up into their story)."""
        b = self.load()

        def agg(entries: list[WorkLogEntry]) -> dict:
            inp = out = 0
            cost = 0.0
            by: dict[str, dict] = defaultdict(
                lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
            for e in entries:
                inp += e.input_tokens
                out += e.output_tokens
                cost += e.cost_usd
                key = e.subagent_type or e.agent or "unknown"
                by[key]["input_tokens"] += e.input_tokens
                by[key]["output_tokens"] += e.output_tokens
                by[key]["cost_usd"] += e.cost_usd
            return {
                "input_tokens": inp, "output_tokens": out, "cost_usd": round(cost, 4),
                "by_agent": sorted(
                    ({"agent": k, **v, "cost_usd": round(v["cost_usd"], 4)} for k, v in by.items()),
                    key=lambda r: r["cost_usd"], reverse=True),
            }

        story_entries: dict[str, list[WorkLogEntry]] = {s.id: list(s.work_log) for s in b.stories}
        for t in b.tasks:
            story_entries.setdefault(t.story_id, []).extend(t.work_log)
        feat_entries: dict[str, list[WorkLogEntry]] = defaultdict(list)
        for s in b.stories:
            feat_entries[s.feature_id].extend(story_entries.get(s.id, []))
        epic_entries: dict[str, list[WorkLogEntry]] = defaultdict(list)
        for f in b.features:
            epic_entries[f.epic_id].extend(feat_entries.get(f.id, []))
        return {
            "stories": {sid: agg(es) for sid, es in story_entries.items()},
            "features": {fid: agg(es) for fid, es in feat_entries.items()},
            "epics": {eid: agg(es) for eid, es in epic_entries.items()},
            "total": agg([e for es in story_entries.values() for e in es]),
        }

    def trace(self, us_id: str | None = None) -> list[dict]:
        """Flatten every work_log entry into a chronological cost trace (optionally one US)."""
        b = self.load()
        title = {s.id: s.title for s in b.stories}
        rows: list[dict] = []

        def row(uid: str, kind: str, e: WorkLogEntry, task_id: str = "") -> dict:
            d = e.model_dump()
            d.update({"us_id": uid, "title": title.get(uid, uid), "kind": kind})
            if task_id:
                d["task_id"] = task_id
            return d

        for s in b.stories:
            if us_id and s.id != us_id:
                continue
            rows.extend(row(s.id, "story", e) for e in s.work_log)
        for t in b.tasks:
            if us_id and t.story_id != us_id:
                continue
            rows.extend(row(t.story_id, "task", e, t.id) for e in t.work_log)
        rows.sort(key=lambda r: r.get("at") or "")
        return rows

    # --- flow metrics (derived from status transitions) ---------------------------------
    def flow_metrics(self, now: str = "", trials: int = 1000, seed: int = 42) -> dict:
        """DORA/Kanban-style flow metrics over story status transitions: cycle time,
        weekly throughput, current WIP + aging, and a Monte-Carlo 'when will the backlog be
        done' forecast. `now` (ISO) anchors WIP aging; `seed` makes the forecast reproducible.
        Requires a transition history (recorded by set_status) — empty until items have moved."""
        import math
        import random as _random
        from collections import Counter
        from datetime import datetime

        def parse(s: str):
            if not s:
                return None
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                return None

        def pct(xs: Sequence[float], p: float):
            if not xs:
                return None
            xs = sorted(xs)
            k = (len(xs) - 1) * p
            f, c = math.floor(k), math.ceil(k)
            return round(xs[int(k)] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f), 2)

        b = self.load()
        now_dt = parse(now)

        cycle_days: list[float] = []
        weeks: Counter = Counter()
        for s in b.stories:
            done_t = next((parse(t.at) for t in s.transitions
                           if t.to_status == "done" and parse(t.at)), None)
            start_t = (next((parse(t.at) for t in s.transitions
                             if t.to_status == "in_progress" and parse(t.at)), None)
                       or next((parse(t.at) for t in s.transitions
                                if t.to_status == "todo" and parse(t.at)), None))
            if done_t and start_t and done_t >= start_t:
                cycle_days.append((done_t - start_t).total_seconds() / 86400.0)
            if done_t:
                iso = done_t.isocalendar()
                weeks[f"{iso[0]}-W{iso[1]:02d}"] += 1

        weekly = list(weeks.values())
        wip_states = {"in_progress", "review"}
        wip = [s for s in b.stories if str(s.status) in wip_states]
        aging: list[dict] = []
        if now_dt:
            for s in wip:
                ent = None
                for t in s.transitions:
                    if t.to_status == str(s.status) and parse(t.at):
                        ent = parse(t.at)
                if ent:
                    aging.append({"id": s.id, "status": str(s.status),
                                  "age_days": round((now_dt - ent).total_seconds() / 86400.0, 2)})

        remaining = [s for s in b.stories if str(s.status) != "done"]
        forecast: dict = {}
        if weekly and remaining:
            rng = _random.Random(seed)
            n = len(remaining)
            sims = []
            for _ in range(trials):
                done = wk = 0
                while done < n and wk < 520:
                    done += rng.choice(weekly)
                    wk += 1
                sims.append(wk)
            forecast = {"items_remaining": n, "weeks_p50": pct(sims, 0.5),
                        "weeks_p85": pct(sims, 0.85)}

        return {
            "cycle_time_days": {
                "count": len(cycle_days),
                "avg": round(sum(cycle_days) / len(cycle_days), 2) if cycle_days else None,
                "p50": pct(cycle_days, 0.5), "p85": pct(cycle_days, 0.85)},
            "throughput_per_week": {
                "weeks": dict(weeks),
                "avg": round(sum(weekly) / len(weekly), 2) if weekly else None},
            "wip": {"count": len(wip), "items": [s.id for s in wip]},
            "aging_wip": sorted(aging, key=lambda x: -x["age_days"]),
            "forecast": forecast,
        }

    def delete(self, kind: str, item_id: str) -> None:
        """Delete an item and cascade to its children."""
        b = self.load()
        self._find(b, kind, item_id)  # raises if absent
        if kind == "epic":
            feats = {f.id for f in b.features if f.epic_id == item_id}
            stories = {s.id for s in b.stories if s.feature_id in feats}
            b.tasks = [t for t in b.tasks if t.story_id not in stories]
            b.stories = [s for s in b.stories if s.id not in stories]
            b.features = [f for f in b.features if f.id not in feats]
            b.epics = [e for e in b.epics if e.id != item_id]
        elif kind == "feature":
            stories = {s.id for s in b.stories if s.feature_id == item_id}
            b.tasks = [t for t in b.tasks if t.story_id not in stories]
            b.stories = [s for s in b.stories if s.id not in stories]
            b.features = [f for f in b.features if f.id != item_id]
        elif kind == "story":
            b.tasks = [t for t in b.tasks if t.story_id != item_id]
            b.stories = [s for s in b.stories if s.id != item_id]
        else:
            b.tasks = [t for t in b.tasks if t.id != item_id]
        self.save(b)
