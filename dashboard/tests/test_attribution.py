"""Per-run attribution (`cli attribute`): distinct real cost per US, idempotent, and
mutually exclusive with whole-session `cli link` (no double-count). Self-contained."""
import json
from pathlib import Path

from backend import cli, telemetry
from backend.board import BoardStore


def _ev(session, inp, out):
    return json.dumps({
        "timestamp": "2026-06-01T10:00:00Z", "sessionId": session, "isSidechain": True,
        "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}},
    })


def _tree(tmp: Path):
    sub = tmp / "claude" / "projects" / "-proj" / "sess" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-R1.meta.json").write_text(json.dumps({"agentType": "fenrir:reviewer"}))
    (sub / "agent-R1.jsonl").write_text(_ev("S1", 1000, 500) + "\n")
    (sub / "agent-R2.meta.json").write_text(json.dumps({"agentType": "coder"}))
    (sub / "agent-R2.jsonl").write_text(_ev("S2", 2000, 800) + "\n")
    return tmp / "claude"


def _board(tmp, monkeypatch):
    cd = _tree(tmp)
    board = tmp / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F")
    s.add_story(f.id, "S1"); s.add_story(f.id, "S2"); s.add_story(f.id, "S3")
    return cd, board


def test_subagent_runs_expose_run_id_and_session(tmp_path):
    runs = telemetry.subagent_runs(_tree(tmp_path), "-proj")["runs"]
    by = {r["run_id"]: r for r in runs}
    assert by["agent-R1"]["agent_type"] == "fenrir:reviewer" and by["agent-R1"]["session_id"] == "S1"
    assert by["agent-R2"]["session_id"] == "S2"


def test_attribute_distinct_real_cost_per_us(monkeypatch, tmp_path):
    _, board = _board(tmp_path, monkeypatch)
    assert cli.main(["attribute", "--kind", "story", "--id", "us-1", "--run", "agent-R1",
                     "--project=-proj"]) == 0
    assert cli.main(["attribute", "--kind", "story", "--id", "us-2", "--run", "agent-R2",
                     "--project=-proj"]) == 0
    bs = BoardStore(board).load()
    w1 = [s for s in bs.stories if s.id == "us-1"][0].work_log
    w2 = [s for s in bs.stories if s.id == "us-2"][0].work_log
    assert w1[0].input_tokens == 1000 and w1[0].subagent_type == "fenrir:reviewer"
    assert w2[0].input_tokens == 2000  # DIFFERENT US -> DIFFERENT real cost
    assert w1[0].cost_usd != w2[0].cost_usd


def test_attribute_idempotent_per_run(monkeypatch, tmp_path):
    _, board = _board(tmp_path, monkeypatch)
    cli.main(["attribute", "--kind", "story", "--id", "us-1", "--run", "agent-R1", "--project=-proj"])
    cli.main(["attribute", "--kind", "story", "--id", "us-1", "--run", "agent-R1", "--project=-proj"])
    wl = [s for s in BoardStore(board).load().stories if s.id == "us-1"][0].work_log
    assert len(wl) == 1  # second attribute is a no-op


def test_attribute_then_link_same_session_refused(monkeypatch, tmp_path, capsys):
    # R1's session is S1; attributing R1 then whole-session linking S1 would double-count
    _, board = _board(tmp_path, monkeypatch)
    cli.main(["attribute", "--kind", "story", "--id", "us-1", "--run", "agent-R1", "--project=-proj"])
    rc = cli.main(["link", "--kind", "story", "--id", "us-3", "--session", "S1", "--project=-proj"])
    assert rc == 1
    assert "per-run attributions" in capsys.readouterr().err


def test_link_then_attribute_same_session_refused(monkeypatch, tmp_path, capsys):
    _, board = _board(tmp_path, monkeypatch)
    cli.main(["link", "--kind", "story", "--id", "us-3", "--session", "S1", "--project=-proj"])
    rc = cli.main(["attribute", "--kind", "story", "--id", "us-1", "--run", "agent-R1", "--project=-proj"])
    assert rc == 1
    assert "mutually exclusive" in capsys.readouterr().err
