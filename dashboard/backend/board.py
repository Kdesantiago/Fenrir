"""Agile board store — Epic → Feature → User Story → Task over a git-tracked JSON file.

LifeOS spirit: the board is plain, reviewable, version-controlled data (`data/board.json`),
not a hidden DB. Both the web API and the CLI (which the agents drive) go through this one
module, so there is a single source of truth.
"""
from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .models import Board, Epic, Feature, Status, Task, Transition, UserStory, WorkLogEntry

DEFAULT_BOARD_PATH = Path(__file__).resolve().parent.parent / "data" / "board.json"

_PREFIX = {"epic": "epic", "feature": "feat", "story": "us", "task": "task"}


class BoardStore:
    def __init__(self, path: Path | None = None, retro_dir: Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_BOARD_PATH
        # Where to drop an epic retrospective when an epic closes. None → auto-write disabled
        # (the lib stays pure; the CLI/app inject a real dir). See `write_epic_retro`.
        self.retro_dir = Path(retro_dir) if retro_dir else None

    # --- persistence -------------------------------------------------------------------
    def load(self) -> Board:
        if not self.path.exists():
            return Board()
        try:
            return Board.model_validate_json(self.path.read_text())
        except Exception:
            return Board()

    def save(self, board: Board) -> None:
        # Atomic write: a crash mid-write (or a racing reader) never sees a half-written /
        # corrupt board — we write a temp file and os.replace (atomic on POSIX).
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(board.model_dump_json(indent=2) + "\n")
        os.replace(tmp, self.path)

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

    @staticmethod
    def _set_status(item: Any, status: Status, at: str) -> None:
        if str(item.status) != str(status):
            item.transitions.append(Transition(from_status=str(item.status), to_status=str(status), at=at))
            item.status = status

    @staticmethod
    def _derive(statuses: list) -> Status | None:
        """Parent status rolled up from its children: all done → done; any active
        (in_progress/review) → in_progress; any todo → todo; else backlog. None if no children
        (keep whatever it has)."""
        s = {str(x) for x in statuses}
        if not s:
            return None
        if s == {"done"}:
            return Status.done
        if "in_progress" in s or "review" in s:
            return Status.in_progress
        if "todo" in s:
            return Status.todo
        return Status.backlog

    def set_status(self, kind: str, item_id: str, status: Status, at: str = "") -> Any:
        b = self.load()
        item = self._find(b, kind, item_id)
        # which epic is affected, and was it already done before this change?
        if kind == "epic":
            epic_id = item_id
        elif kind == "feature":
            epic_id = item.epic_id
        elif kind == "story":
            epic_id = self._epic_of_feature(b, item.feature_id)
        else:  # task — no status rollup, no epic close to detect
            epic_id = ""
        was_done = any(str(e.status) == "done" for e in b.epics if e.id == epic_id)
        self._set_status(item, status, at)
        # Roll the change UP: a US drives its feature + epic; a (manually-dragged) feature drives
        # its epic; an epic is terminal. The item just set is respected; parents are derived from
        # children, so a manual feature/epic status holds until a child US changes again.
        if kind == "story":
            feat = next((f for f in b.features if f.id == item.feature_id), None)
            if feat:
                d = self._derive([s.status for s in b.stories if s.feature_id == feat.id])
                if d:
                    self._set_status(feat, d, at)
                self._rollup_epic(b, feat.epic_id, at)
        elif kind == "feature":
            self._rollup_epic(b, item.epic_id, at)
        now_done = any(str(e.status) == "done" for e in b.epics if e.id == epic_id)
        self.save(b)
        # Epic just CLOSED → auto-write its retrospective (best-effort, never blocks the move).
        if epic_id and now_done and not was_done and self.retro_dir:
            try:
                self.write_epic_retro(epic_id)
            except Exception:
                pass
        return item

    @staticmethod
    def _epic_of_feature(b: Board, feature_id: str) -> str:
        f = next((x for x in b.features if x.id == feature_id), None)
        return f.epic_id if f else ""

    def _rollup_epic(self, b: Board, epic_id: str, at: str) -> None:
        ep = next((e for e in b.epics if e.id == epic_id), None)
        if not ep:
            return
        d = self._derive([f.status for f in b.features if f.epic_id == ep.id])
        if d:
            self._set_status(ep, d, at)

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
            inp = out = cw = cr = 0
            cost = 0.0
            by: dict[str, dict] = defaultdict(
                lambda: {"input_tokens": 0, "output_tokens": 0,
                         "cache_write_tokens": 0, "cache_read_tokens": 0, "cost_usd": 0.0})
            for e in entries:
                inp += e.input_tokens
                out += e.output_tokens
                cw += e.cache_write_tokens
                cr += e.cache_read_tokens
                cost += e.cost_usd
                key = e.subagent_type or e.agent or "unknown"
                by[key]["input_tokens"] += e.input_tokens
                by[key]["output_tokens"] += e.output_tokens
                by[key]["cache_write_tokens"] += e.cache_write_tokens
                by[key]["cache_read_tokens"] += e.cache_read_tokens
                by[key]["cost_usd"] += e.cost_usd
            return {
                "input_tokens": inp, "output_tokens": out,
                "cache_write_tokens": cw, "cache_read_tokens": cr, "cost_usd": round(cost, 4),
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

    # --- epic retrospective (auto-written on epic close) -------------------------------
    @staticmethod
    def _slug(text: str) -> str:
        s = "".join(c.lower() if c.isalnum() else "-" for c in text)
        while "--" in s:
            s = s.replace("--", "-")
        return s.strip("-")[:48] or "epic"

    @staticmethod
    def _reopened(item: Any) -> bool:
        """A status moved BACKWARD at some point (done→… or in_progress→backlog) = rework signal."""
        rank = {"backlog": 0, "todo": 1, "in_progress": 2, "review": 3, "done": 4}
        for t in item.transitions:
            if rank.get(str(t.to_status), 0) < rank.get(str(t.from_status), 0):
                return True
        return False

    def epic_retro_doc(self, epic_id: str) -> str:
        """Render an epic's retrospective as Markdown from board facts: what shipped, the real
        cost rollup (Epic = Σ Features = Σ US), flow span, a timeline, and SEEDED qualitative
        sections (worked / didn't / revisit) primed from real signals (audit smells, rework,
        expensive US) so the doc is never blank. The delivery-tracker agent refines the prose."""
        b = self.load()
        ep = next((e for e in b.epics if e.id == epic_id), None)
        if not ep:
            raise KeyError(f"epic {epic_id} not found")
        c = self.costs()
        feats = [f for f in b.features if f.epic_id == epic_id]
        feat_ids = {f.id for f in feats}
        stories = [s for s in b.stories if s.feature_id in feat_ids]
        story_by_feat: dict[str, list] = defaultdict(list)
        for s in stories:
            story_by_feat[s.feature_id].append(s)

        def usd(x: float) -> str:
            return f"${x:,.2f}"

        ecost = c["epics"].get(epic_id, {})

        # opened/closed span from transitions across the epic + its children
        all_ts = list(ep.transitions) + [t for f in feats for t in f.transitions] + \
                 [t for s in stories for t in s.transitions]
        ats = sorted(t.at for t in all_ts if t.at)
        opened, closed = (ats[0][:10] if ats else "?"), (ats[-1][:10] if ats else "?")

        lines: list[str] = []
        lines.append(f"# Retrospective — {ep.title} (`{epic_id}`)")
        lines.append("")
        lines.append("> Auto-generated by Fenrir when this epic closed. Facts come from the board; "
                     "the **What worked / didn't / revisit** sections are seeded from real signals "
                     "— refine them (the `delivery-tracker` agent can enrich). Revisit when planning "
                     "the next epic.")
        lines.append("")
        lines.append(f"- **Opened → Closed:** {opened} → {closed}")
        lines.append(f"- **Features:** {len(feats)}  ·  **User Stories:** {len(stories)} "
                     f"(all done)  ·  **Status:** {ep.status}")
        lines.append(f"- **Real cost (with caching):** {usd(ecost.get('cost_usd', 0.0))} "
                     f"— in {ecost.get('input_tokens', 0):,} · out {ecost.get('output_tokens', 0):,} "
                     f"· cacheR {ecost.get('cache_read_tokens', 0):,} · cacheW "
                     f"{ecost.get('cache_write_tokens', 0):,} tok")
        lines.append("")

        # Outcome table
        lines.append("## What shipped")
        lines.append("")
        lines.append("| Feature | Cost | User Stories |")
        lines.append("|---|---|---|")
        for f in feats:
            fc = c["features"].get(f.id, {}).get("cost_usd", 0.0)
            us_cells = "<br>".join(
                f"`{s.id}` {s.title} — {usd(c['stories'].get(s.id, {}).get('cost_usd', 0.0))}"
                for s in story_by_feat.get(f.id, []))
            lines.append(f"| **{f.title}** (`{f.id}`) | {usd(fc)} | {us_cells or '—'} |")
        lines.append("")
        lines.append(f"**Rollup check:** Epic {usd(ecost.get('cost_usd', 0.0))} "
                     f"= Σ Features = Σ User Stories.")
        lines.append("")

        # Timeline (compact)
        lines.append("## Timeline")
        lines.append("")
        for tr in sorted(ep.transitions, key=lambda x: x.at):
            lines.append(f"- `{tr.at[:19]}` epic **{tr.from_status} → {tr.to_status}**")
        lines.append("")

        # Seeded qualitative sections from real signals
        au = self.audit()
        umbrellas = [u for u in au.get("coarse_us", []) if u.get("id") in {s.id for s in stories}]
        pricey = [u for u in au.get("expensive_us", []) if u.get("id") in {s.id for s in stories}]
        reworked = [s for s in stories if self._reopened(s)]
        top_us = sorted(stories, key=lambda s: -c["stories"].get(s.id, {}).get("cost_usd", 0.0))

        lines.append("## What worked")
        lines.append("")
        lines.append(f"- Delivered {len(stories)} US across {len(feats)} features; status rollup "
                     "auto-closed the epic when the last US merged.")
        if top_us:
            tu = top_us[0]
            lines.append(f"- Highest-value US: `{tu.id}` {tu.title} "
                         f"({usd(c['stories'].get(tu.id, {}).get('cost_usd', 0.0))}).")
        lines.append("- _(add: what to repeat — patterns, agents, decisions that paid off)_")
        lines.append("")

        lines.append("## What didn't / friction")
        lines.append("")
        if umbrellas:
            lines.append(f"- **Non-atomic US (umbrellas):** {', '.join('`'+u['id']+'`' for u in umbrellas)} "
                         "held an outsized share of cost — decompose next time.")
        if reworked:
            lines.append(f"- **Rework:** {', '.join('`'+s.id+'`' for s in reworked)} bounced backward "
                         "(reopened/blocked) — scope or acceptance criteria were unclear.")
        if not umbrellas and not reworked:
            lines.append("- No structural smells flagged (atomic US, no rework). _(add real friction.)_")
        lines.append("- _(add: where time leaked — flaky gates, unclear specs, context churn)_")
        lines.append("")

        lines.append("## Decisions to revisit")
        lines.append("")
        if pricey:
            lines.append("- **Expensive-but-atomic US** (optimize, don't necessarily split): "
                         + ", ".join(f"`{u['id']}` ({usd(u.get('cost_usd', 0.0))})" for u in pricey) + ".")
        lines.append("- _(add: assumptions/tech choices to re-examine; link the ADRs in `docs/adr/`)_")
        lines.append("")

        lines.append("## Follow-ups")
        lines.append("- _(open items carried into the next epic)_")
        lines.append("")
        lines.append("## References")
        lines.append("- PRs: _(list the merged PRs for this epic)_  ·  Specs: `docs/specs/`  ·  "
                     "ADRs: `docs/adr/`  ·  Board: this epic's US")
        lines.append("")
        return "\n".join(lines)

    def write_epic_retro(self, epic_id: str, out: Path | None = None, force: bool = False) -> Path:
        """Write the epic retro to `out` (or `<retro_dir>/<epic>-<slug>.md`). Does NOT clobber an
        existing file unless `force` — so human-refined worked/didn't notes survive a re-close.
        Returns the path (existing path if skipped)."""
        b = self.load()
        ep = next((e for e in b.epics if e.id == epic_id), None)
        if not ep:
            raise KeyError(f"epic {epic_id} not found")
        if out is None:
            base = self.retro_dir or (self.path.parent / "retros")
            out = Path(base) / f"{epic_id}-{self._slug(ep.title)}.md"
        out = Path(out)
        if out.exists() and not force:
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.epic_retro_doc(epic_id))
        return out

    def audit(self, coarse_usd: float = 50.0, dominance: float = 0.4) -> dict:
        """Agile-hygiene check: flag US that are NOT atomic + structural smells.

        A US is COARSE (an umbrella, not one atomic thing) if its real cost exceeds
        `coarse_usd`, or if it carries more than `dominance` of its whole epic's cost — both
        signal "decompose me into the real atomic US". Also flags orphan US (no feature),
        empty features (no US), and epics whose cost sits almost entirely on one US."""
        b = self.load()
        c = self.costs()
        feat_epic = {f.id: f.epic_id for f in b.features}
        feat_ids = {f.id for f in b.features}
        epic_ids = {e.id for e in b.epics}
        stories_of_feat: dict[str, int] = defaultdict(int)
        us_per_epic: dict[str, int] = defaultdict(int)
        for s in b.stories:
            stories_of_feat[s.feature_id] += 1
            us_per_epic[feat_epic.get(s.feature_id, "")] += 1

        # An UMBRELLA US dominates a MULTI-US epic (≥3 US) — that is the non-atomic anti-pattern.
        # Dominance alone in a 1-2 US epic is meaningless (a lone US is trivially 100%), and high
        # COST alone is not non-atomicity (one hard migration / a deep research run is atomic but
        # expensive) — that's surfaced separately as `expensive_us` (informational: optimize, not
        # necessarily decompose).
        coarse: list[dict] = []
        expensive: list[dict] = []
        orphans: list[dict] = []
        for s in b.stories:
            cost = c["stories"].get(s.id, {}).get("cost_usd", 0.0)
            if s.feature_id not in feat_ids:
                orphans.append({"id": s.id, "title": s.title, "issue": "US has no parent feature"})
            epic_id = feat_epic.get(s.feature_id, "")
            epic_cost = c["epics"].get(epic_id, {}).get("cost_usd", 0.0)
            share = (cost / epic_cost) if epic_cost > 0 else 0.0
            if share > dominance and us_per_epic[epic_id] >= 3:
                coarse.append({"id": s.id, "title": s.title, "cost_usd": round(cost, 4),
                               "epic_share": round(share, 3),
                               "reason": f"holds {round(share * 100)}% of a {us_per_epic[epic_id]}-US "
                                         "epic's cost — likely an umbrella, not atomic",
                               "fix": "decompose into the real atomic US (one per thing done) "
                                      "and re-attribute"})
            elif cost > coarse_usd:
                expensive.append({"id": s.id, "title": s.title, "cost_usd": round(cost, 4),
                                  "note": "expensive but may be atomic — optimize (see cache "
                                          "efficiency), only decompose if it does >1 thing"})
        empty_features = [{"id": f.id, "title": f.title} for f in b.features
                          if stories_of_feat[f.id] == 0]
        empty_features += [{"id": f.id, "title": f.title, "issue": "feature has no parent epic"}
                           for f in b.features if f.epic_id not in epic_ids]
        coarse.sort(key=lambda x: -x["cost_usd"])
        expensive.sort(key=lambda x: -x["cost_usd"])
        return {
            "coarse_us": coarse, "expensive_us": expensive, "orphan_us": orphans,
            "empty_features": empty_features,
            "thresholds": {"coarse_usd": coarse_usd, "dominance": dominance},
            "ok": not (coarse or orphans or empty_features),
        }

    def trace(self, us_id: str | None = None, feature_id: str | None = None,
              epic_id: str | None = None, newest_first: bool = True) -> list[dict]:
        """Flatten every work_log entry into a cost trace, optionally scoped to one US / Feature /
        Epic. Each row carries its `us_id`/`feature_id`/`epic_id` so the UI can filter + group.
        Sorted by date, **newest first by default** (the arrivals view — recent work is what you
        look at; sort-by-cost is a UI toggle, not the default)."""
        b = self.load()
        title = {s.id: s.title for s in b.stories}
        feat_of = {s.id: s.feature_id for s in b.stories}
        epic_of_feat = {f.id: f.epic_id for f in b.features}

        def epic_of(uid: str) -> str:
            return epic_of_feat.get(feat_of.get(uid, ""), "")

        def keep(uid: str) -> bool:
            if us_id and uid != us_id:
                return False
            if feature_id and feat_of.get(uid, "") != feature_id:
                return False
            if epic_id and epic_of(uid) != epic_id:
                return False
            return True

        rows: list[dict] = []

        def row(uid: str, kind: str, e: WorkLogEntry, task_id: str = "") -> dict:
            d = e.model_dump()
            d.update({"us_id": uid, "title": title.get(uid, uid), "kind": kind,
                      "feature_id": feat_of.get(uid, ""), "epic_id": epic_of(uid)})
            if task_id:
                d["task_id"] = task_id
            return d

        for s in b.stories:
            if not keep(s.id):
                continue
            rows.extend(row(s.id, "story", e) for e in s.work_log)
        for t in b.tasks:
            if not keep(t.story_id):
                continue
            rows.extend(row(t.story_id, "task", e, t.id) for e in t.work_log)
        rows.sort(key=lambda r: r.get("at") or "", reverse=newest_first)
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
