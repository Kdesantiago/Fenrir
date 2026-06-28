"""Tests for per-US cost rollup, the cost trace, subagent attribution (reconciled, no
double-count), tier-stripped pricing, and the idempotent per-source `cli link`.
Self-contained; redirects board + ~/.claude via env/args so nothing real is touched.
"""
import json

import pytest

from backend import cli, pricing, telemetry
from backend.board import BoardStore
from backend.models import WorkLogEntry


def _ev(session: str, inp: int = 1000, out: int = 500, sidechain: bool = False,
        model: str = "claude-opus-4-8") -> str:
    return json.dumps({
        "timestamp": "2026-06-01T10:00:00Z", "sessionId": session, "isSidechain": sidechain,
        "message": {"model": model, "usage": {
            "input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}},
    })


# --- pricing tier suffix ---
def test_pricing_strips_tier_suffix():
    # the [1m] tier suffix is stripped before family matching
    assert pricing.rates_for("claude-opus-4-8[1m]") == pricing.rates_for("claude-opus-4-8")
    assert pricing.rates_for("claude-opus-4-8[1m]")["input"] == 5.0
    assert pricing.rates_for("claude-sonnet-4-6[1m]")["input"] == 3.0


def test_cost_1h_cache_write_dearer_than_5m():
    # equal cache-write tokens cost MORE at the 1h TTL (2x input) than 5m (1.25x input)
    n = 1_000_000
    c5 = pricing.cost_of({"cache_creation": {"ephemeral_5m_input_tokens": n}}, "claude-opus-4-8")
    c1 = pricing.cost_of({"cache_creation": {"ephemeral_1h_input_tokens": n}}, "claude-opus-4-8")
    assert c1 > c5
    assert c5 == 6.25 and c1 == 10.0  # opus 4.8: 5×1.25 vs 5×2.0


def test_thinking_counted_as_output():
    # extended-thinking tokens are billed as output (no separate field), so output covers them
    assert pricing.cost_of({"output_tokens": 1_000_000}, "claude-opus-4-8") == 25.0


# --- subagent_runs: identity from meta, tokens from .jsonl, reconciled ---
def test_subagent_runs_reconcile_no_double_count(tmp_path):
    cd = tmp_path / "claude"
    sub = cd / "projects" / "-proj" / "sess1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-X.meta.json").write_text(json.dumps(
        {"agentType": "fenrir:reviewer", "description": "review the diff", "toolUseId": "t1"}))
    (sub / "agent-X.jsonl").write_text(_ev("subsess", sidechain=True) + "\n"
                                       + _ev("subsess", sidechain=True) + "\n")
    r = telemetry.subagent_runs(cd, "-proj")
    assert len(r["runs"]) == 1
    run = r["runs"][0]
    assert run["agent_type"] == "fenrir:reviewer"
    assert run["input_tokens"] == 2000 and run["output_tokens"] == 1000
    assert run["cost_usd"] > 0 and run["attributed"] is True
    # the key invariant the red-team demanded: no double-count
    assert r["attributed_tokens"] + r["unattributed_tokens"] == r["subagent_total_tokens"]
    assert r["attributed_tokens"] == 3000


def test_subagent_runs_missing_transcript_is_unattributed(tmp_path):
    cd = tmp_path / "claude"
    sub = cd / "projects" / "-proj" / "s" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-Y.meta.json").write_text(json.dumps({"agentType": "general-purpose"}))
    # no agent-Y.jsonl -> run recorded but 0 tokens, status no-transcript
    r = telemetry.subagent_runs(cd, "-proj")
    assert r["runs"][0]["status"] == "no-transcript"
    assert r["runs"][0]["attributed"] is False


# --- board.costs() rollup ---
def _board_with_work(tmp_path) -> BoardStore:
    s = BoardStore(tmp_path / "board.json")
    e = s.add_epic("E"); f = s.add_feature(e.id, "F"); st = s.add_story(f.id, "S")
    t = s.add_task(st.id, "T")
    s.log_work("story", st.id, WorkLogEntry(agent="architect", input_tokens=1000,
                                            output_tokens=500, cost_usd=0.10, at="2026-06-01"))
    s.log_work("task", t.id, WorkLogEntry(agent="coder", input_tokens=200,
                                          output_tokens=100, cost_usd=0.02, at="2026-06-02"))
    return s


def test_costs_rollup_with_by_agent(tmp_path):
    c = _board_with_work(tmp_path).costs()
    us = c["stories"]["us-1"]
    assert us["input_tokens"] == 1200 and us["output_tokens"] == 600  # task rolls into story
    assert round(us["cost_usd"], 2) == 0.12
    agents = {a["agent"]: a for a in us["by_agent"]}
    assert set(agents) == {"architect", "coder"}
    assert c["epics"]["epic-1"]["cost_usd"] == c["total"]["cost_usd"] == round(0.12, 4)


def test_trace_flatten_and_filter(tmp_path):
    s = _board_with_work(tmp_path)
    allrows = s.trace(newest_first=False)  # ascending, to assert chronological order explicitly
    assert len(allrows) == 2
    assert [r["kind"] for r in allrows] == ["story", "task"]  # sorted by `at` (oldest first)
    assert [r["kind"] for r in s.trace()] == ["task", "story"]  # default is now newest-first
    only = s.trace("us-1")
    assert len(only) == 2 and all(r["us_id"] == "us-1" for r in only)


# --- cli link: idempotent + per-source grouping ---
def test_cli_link_idempotent_and_per_source(monkeypatch, tmp_path):
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj" / "s"
    proj.mkdir(parents=True)
    (proj / "main.jsonl").write_text(_ev("S1", sidechain=False) + "\n")
    (proj / "sub.jsonl").write_text(_ev("S1", sidechain=True) + "\n")
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F"); st = s.add_story(f.id, "S")

    assert cli.main(["link", "--kind", "story", "--id", st.id, "--session", "S1",
                     "--project=-proj"]) == 0
    wl = [x for x in BoardStore(board).load().stories if x.id == st.id][0].work_log
    assert len(wl) == 2  # one per source: main + subagent
    assert {w.source for w in wl} == {"telemetry-link"}
    assert {w.agent for w in wl} == {"main", "subagent"}

    # second identical link is a no-op (idempotent per session+US)
    assert cli.main(["link", "--kind", "story", "--id", st.id, "--session", "S1",
                     "--project=-proj"]) == 0
    wl2 = [x for x in BoardStore(board).load().stories if x.id == st.id][0].work_log
    assert len(wl2) == 2


def test_cli_link_captures_cache_and_refresh_updates(monkeypatch, tmp_path):
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj" / "s"
    proj.mkdir(parents=True)
    ev = json.dumps({
        "timestamp": "2026-06-01T10:00:00Z", "sessionId": "S1", "isSidechain": False,
        "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": 1000, "output_tokens": 500,
            "cache_creation_input_tokens": 2000, "cache_read_input_tokens": 40000}}})
    p = proj / "main.jsonl"
    p.write_text(ev + "\n")
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F"); st = s.add_story(f.id, "S")

    cli.main(["link", "--kind", "story", "--id", st.id, "--session", "S1", "--project=-proj"])
    w = [x for x in BoardStore(board).load().stories if x.id == st.id][0].work_log[0]
    assert w.cache_write_tokens == 2000 and w.cache_read_tokens == 40000  # cache persisted

    rollup = BoardStore(board).costs()["stories"][st.id]
    assert rollup["cache_write_tokens"] == 2000 and rollup["cache_read_tokens"] == 40000

    # a second event accrues; --refresh re-links with current totals (still one entry, no dup)
    p.write_text(ev + "\n" + ev + "\n")
    cli.main(["link", "--kind", "story", "--id", st.id, "--session", "S1",
              "--project=-proj", "--refresh"])
    wl = [x for x in BoardStore(board).load().stories if x.id == st.id][0].work_log
    assert len(wl) == 1 and wl[0].cache_read_tokens == 80000  # refreshed, not doubled-up


def test_audit_flags_umbrella_but_not_expensive_atomic(tmp_path):
    s = BoardStore(tmp_path / "b.json")
    # epic with 3 US, one dominating → umbrella (the real non-atomic anti-pattern)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    big = s.add_story(f.id, "umbrella")
    a1 = s.add_story(f.id, "atomic1"); a2 = s.add_story(f.id, "atomic2")
    s.log_work("story", big.id, WorkLogEntry(agent="x", cost_usd=300.0))
    s.log_work("story", a1.id, WorkLogEntry(agent="x", cost_usd=2.0))
    s.log_work("story", a2.id, WorkLogEntry(agent="x", cost_usd=2.0))
    au = s.audit(coarse_usd=50.0, dominance=0.4)
    coarse = {u["id"] for u in au["coarse_us"]}
    assert big.id in coarse  # dominates a 3-US epic
    assert a1.id not in coarse and a2.id not in coarse
    assert au["ok"] is False

    # a lone expensive US in its own epic is ATOMIC-but-costly → expensive_us, NOT coarse
    e2 = s.add_epic("E2"); f2 = s.add_feature(e2.id, "F2")
    exp = s.add_story(f2.id, "expensive-atomic")
    s.log_work("story", exp.id, WorkLogEntry(agent="x", cost_usd=80.0))
    au2 = s.audit()
    assert exp.id not in {u["id"] for u in au2["coarse_us"]}      # 1-US epic ≠ umbrella
    assert exp.id in {u["id"] for u in au2["expensive_us"]}        # but surfaced as expensive

    s.add_feature(e.id, "empty")  # a feature with no US is a structural smell
    assert any(x["id"] for x in s.audit()["empty_features"])


def _subrun(proj, rid, ts, inp, out):
    (proj / f"{rid}.meta.json").write_text(json.dumps({"agentType": "workflow-subagent"}))
    (proj / f"{rid}.jsonl").write_text(json.dumps({
        "timestamp": ts, "sessionId": "S1", "isSidechain": True,
        "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}}) + "\n")


def test_reconcile_attributes_per_us_by_time_and_rolls_up(monkeypatch, tmp_path):
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj"
    proj.mkdir(parents=True)
    (proj / "main.jsonl").write_text(_ev("S1", inp=1000, out=500) + "\n")  # main thread
    _subrun(proj, "agent-r1", "2026-06-01T08:00:00Z", 1000, 100)  # before noon → us-A
    _subrun(proj, "agent-r2", "2026-06-01T14:00:00Z", 2000, 200)  # after noon  → us-B
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    a_us = s.add_story(f.id, "A"); b_us = s.add_story(f.id, "B")
    uslog = tmp_path / "uslog.jsonl"
    uslog.write_text(f'{{"at":"2026-06-01T00:00:00+00:00","us":"{a_us.id}"}}\n'
                     f'{{"at":"2026-06-01T12:00:00+00:00","us":"{b_us.id}"}}\n')
    wm = tmp_path / "wm.json"
    args = ["reconcile", "--session", "S1", "--current-us", b_us.id,
            "--uslog", str(uslog), "--watermark", str(wm), "--project=-proj"]
    assert cli.main(args) == 0

    c = BoardStore(board).costs()
    ca, cb = c["stories"][a_us.id]["cost_usd"], c["stories"][b_us.id]["cost_usd"]
    assert ca > 0 and cb > 0
    # TIME-SWEPT main: the main event (default _ev ts 10:00) is < the us-B boundary (12:00),
    # so it buckets to us-A — NOT lumped on --current-us (us-B). So A = r1 + main, B = r2.
    assert ca > cb                                  # A now carries the main-thread bucket
    # rollup: feature = ΣUS, epic = Σfeatures
    assert c["features"][f.id]["cost_usd"] == pytest.approx(ca + cb, abs=0.001)
    assert c["epics"][e.id]["cost_usd"] == pytest.approx(c["features"][f.id]["cost_usd"], abs=0.001)

    # idempotent: re-run adds nothing (runs seen, watermark caught up)
    assert cli.main(args) == 0
    c2 = BoardStore(board).costs()
    assert c2["stories"][a_us.id]["cost_usd"] == pytest.approx(ca, abs=0.001)
    assert c2["stories"][b_us.id]["cost_usd"] == pytest.approx(cb, abs=0.001)


# --- reconcile: TIME-SWEPT main-thread attribution (each main event → US active when it ran) ---
def _main_ev(session: str, ts: str, inp: int = 1000, out: int = 500) -> str:
    """A single main-thread (not sidechain) usage event at an explicit timestamp."""
    return json.dumps({
        "timestamp": ts, "sessionId": session, "isSidechain": False,
        "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}})


def _main_entries(board_path, us_id, session):
    return [w for x in BoardStore(board_path).load().stories if x.id == us_id
            for w in x.work_log
            if w.session_id == session and w.source == "telemetry-main"]


def test_reconcile_main_split_across_us_by_timeline(monkeypatch, tmp_path):
    # >=3 main events at T1<T2<T3; uslog: us-A@T0, us-B@(between T2,T3).
    # Events <= the us-B boundary land on us-A; the later one on us-B. Cost SPLITS,
    # it is NOT all lumped on --current-us (us-B).
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj"
    proj.mkdir(parents=True)
    (proj / "main.jsonl").write_text(
        _main_ev("S1", "2026-06-01T09:00:00Z", inp=1000, out=100) + "\n"   # T1 -> us-A
        + _main_ev("S1", "2026-06-01T10:00:00Z", inp=1000, out=100) + "\n"  # T2 -> us-A
        + _main_ev("S1", "2026-06-01T14:00:00Z", inp=5000, out=500) + "\n")  # T3 -> us-B
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    a_us = s.add_story(f.id, "A"); b_us = s.add_story(f.id, "B")
    uslog = tmp_path / "uslog.jsonl"
    uslog.write_text(f'{{"at":"2026-06-01T00:00:00+00:00","us":"{a_us.id}"}}\n'      # T0
                     f'{{"at":"2026-06-01T12:00:00+00:00","us":"{b_us.id}"}}\n')     # between T2,T3
    args = ["reconcile", "--session", "S1", "--current-us", b_us.id,
            "--uslog", str(uslog), "--watermark", str(tmp_path / "wm.json"),
            "--project=-proj"]
    assert cli.main(args) == 0

    a_main = _main_entries(board, a_us.id, "S1")
    b_main = _main_entries(board, b_us.id, "S1")
    assert len(a_main) == 1 and len(b_main) == 1               # one bucketed entry per US
    # us-A got the two early events (2000 in, 200 out); us-B got the one late event (5000/500)
    assert a_main[0].input_tokens == 2000 and a_main[0].output_tokens == 200
    assert b_main[0].input_tokens == 5000 and b_main[0].output_tokens == 500
    # cost genuinely split (NOT all on current-us)
    assert a_main[0].cost_usd > 0 and b_main[0].cost_usd > 0
    assert b_main[0].cost_usd > a_main[0].cost_usd            # bigger late event


def test_reconcile_main_idempotent_full_recompute(monkeypatch, tmp_path):
    # Run reconcile twice: each US keeps exactly ONE telemetry-main entry and totals are
    # identical (full-recompute drops prior entries, no doubling).
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj"
    proj.mkdir(parents=True)
    (proj / "main.jsonl").write_text(
        _main_ev("S1", "2026-06-01T09:00:00Z", inp=1000, out=100) + "\n"
        + _main_ev("S1", "2026-06-01T14:00:00Z", inp=5000, out=500) + "\n")
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    a_us = s.add_story(f.id, "A"); b_us = s.add_story(f.id, "B")
    uslog = tmp_path / "uslog.jsonl"
    uslog.write_text(f'{{"at":"2026-06-01T00:00:00+00:00","us":"{a_us.id}"}}\n'
                     f'{{"at":"2026-06-01T12:00:00+00:00","us":"{b_us.id}"}}\n')
    args = ["reconcile", "--session", "S1", "--current-us", b_us.id,
            "--uslog", str(uslog), "--project=-proj"]
    assert cli.main(args) == 0
    c1 = BoardStore(board).costs()
    a1, b1 = c1["stories"][a_us.id]["cost_usd"], c1["stories"][b_us.id]["cost_usd"]

    assert cli.main(args) == 0  # second run
    assert len(_main_entries(board, a_us.id, "S1")) == 1   # exactly one each, not doubled
    assert len(_main_entries(board, b_us.id, "S1")) == 1
    c2 = BoardStore(board).costs()
    assert c2["stories"][a_us.id]["cost_usd"] == pytest.approx(a1, abs=1e-9)
    assert c2["stories"][b_us.id]["cost_usd"] == pytest.approx(b1, abs=1e-9)


def test_reconcile_main_recompute_preserves_subagent_entries(monkeypatch, tmp_path):
    # A telemetry-run (subagent) entry for the session must survive the main re-compute.
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj"
    proj.mkdir(parents=True)
    (proj / "main.jsonl").write_text(_main_ev("S1", "2026-06-01T14:00:00Z", inp=2000, out=200) + "\n")
    _subrun(proj, "agent-r1", "2026-06-01T14:30:00Z", 3000, 300)  # subagent run -> us-B
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    a_us = s.add_story(f.id, "A"); b_us = s.add_story(f.id, "B")
    uslog = tmp_path / "uslog.jsonl"
    uslog.write_text(f'{{"at":"2026-06-01T00:00:00+00:00","us":"{a_us.id}"}}\n'
                     f'{{"at":"2026-06-01T12:00:00+00:00","us":"{b_us.id}"}}\n')
    args = ["reconcile", "--session", "S1", "--current-us", b_us.id,
            "--uslog", str(uslog), "--project=-proj"]
    assert cli.main(args) == 0
    assert cli.main(args) == 0  # re-run: main is full-recomputed, subagent must persist

    runs = [w for x in BoardStore(board).load().stories
            for w in x.work_log if w.source == "telemetry-run" and w.run_id == "agent-r1"]
    assert len(runs) == 1                                    # subagent entry survived, once
    assert runs[0].input_tokens == 3000 and runs[0].output_tokens == 300


def test_reconcile_main_fallback_to_current_us_before_first_uslog(monkeypatch, tmp_path):
    # An event BEFORE the first uslog boundary falls back to --current-us.
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj"
    proj.mkdir(parents=True)
    # event at 06:00 is before the first uslog entry (08:00) -> fallback to current-us (us-B)
    (proj / "main.jsonl").write_text(_main_ev("S1", "2026-06-01T06:00:00Z", inp=1500, out=150) + "\n")
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    a_us = s.add_story(f.id, "A"); b_us = s.add_story(f.id, "B")
    uslog = tmp_path / "uslog.jsonl"
    uslog.write_text(f'{{"at":"2026-06-01T08:00:00+00:00","us":"{a_us.id}"}}\n')  # first @08:00
    args = ["reconcile", "--session", "S1", "--current-us", b_us.id,
            "--uslog", str(uslog), "--project=-proj"]
    assert cli.main(args) == 0

    assert _main_entries(board, a_us.id, "S1") == []          # nothing on us-A
    fb = _main_entries(board, b_us.id, "S1")                  # all on current-us (us-B)
    assert len(fb) == 1 and fb[0].input_tokens == 1500


def test_reconcile_tops_up_a_run_that_grew(monkeypatch, tmp_path):
    # a run reconciled while still streaming (partial tokens) must be TOPPED UP later,
    # not frozen at the partial count (the critical mid-stream-freeze fix), and never duplicated.
    cd = tmp_path / "claude"
    proj = cd / "projects" / "-proj"
    proj.mkdir(parents=True)
    _subrun(proj, "agent-r1", "2026-06-01T08:00:00Z", 1000, 100)  # partial
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F"); us = s.add_story(f.id, "A")
    uslog = tmp_path / "uslog.jsonl"
    uslog.write_text(f'{{"at":"2026-06-01T00:00:00+00:00","us":"{us.id}"}}\n')
    args = ["reconcile", "--session", "S1", "--current-us", us.id,
            "--uslog", str(uslog), "--project=-proj"]
    assert cli.main(args) == 0
    c1 = BoardStore(board).costs()["stories"][us.id]["cost_usd"]

    _subrun(proj, "agent-r1", "2026-06-01T08:00:00Z", 5000, 500)  # the run finished growing
    assert cli.main(args) == 0
    rows = [w for x in BoardStore(board).load().stories if x.id == us.id
            for w in x.work_log if w.run_id == "agent-r1"]
    assert len(rows) == 1  # topped up in place, not duplicated
    assert BoardStore(board).costs()["stories"][us.id]["cost_usd"] > c1  # cost grew
