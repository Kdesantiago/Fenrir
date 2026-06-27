"""Tests for the project-scoping + telemetry-link additions (telemetry helpers, the
/api/projects + ?project= API, and the CLI `link` that pulls real telemetry into a
work_log). Self-contained; redirects board + ~/.claude via env so nothing real is touched.
"""
import json
from pathlib import Path

from backend import cli, telemetry
from backend.board import BoardStore


def _ev(session: str, model: str = "claude-opus-4-8", inp: int = 1000, out: int = 500,
        skill: str = "") -> str:
    return json.dumps({
        "timestamp": "2026-06-01T10:00:00Z", "sessionId": session, "isSidechain": False,
        "attributionSkill": skill,
        "message": {"model": model, "usage": {
            "input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}},
    })


def _fake_claude(tmp: Path) -> Path:
    cd = tmp / "claude"
    (cd / "projects" / "-proj-a").mkdir(parents=True)
    (cd / "projects" / "-proj-b").mkdir(parents=True)
    (cd / "projects" / "-proj-a" / "s1.jsonl").write_text(_ev("S1") + "\n" + _ev("S1") + "\n")
    (cd / "projects" / "-proj-b" / "s2.jsonl").write_text(_ev("S2") + "\n")
    return cd


# --- telemetry helpers ---
def test_encode_project():
    assert telemetry.encode_project(Path("/a/b.c")) == "-a-b-c"


def test_list_projects(tmp_path):
    cd = _fake_claude(tmp_path)
    assert telemetry.list_projects(cd) == ["-proj-a", "-proj-b"]


def test_current_project_slug_prefix_match(tmp_path):
    cd = _fake_claude(tmp_path)
    # a cwd inside "-proj-a" (its encoding has the slug as a prefix) resolves to -proj-a
    enc_sub = Path("/proj/a/sub")  # encodes to -proj-a-sub
    assert telemetry.encode_project(enc_sub) == "-proj-a-sub"
    assert telemetry.current_project_slug(cd, Path("/proj/a/sub")) == "-proj-a"
    assert telemetry.current_project_slug(cd, Path("/nowhere")) is None


# --- API: /api/projects + ?project= scoping ---
def _client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from backend.app import app
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(_fake_claude(tmp_path)))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(tmp_path / "board.json"))
    return TestClient(app)


def test_api_projects_lists_slugs(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    body = c.get("/api/projects").json()
    assert set(body["projects"]) == {"-proj-a", "-proj-b"}


def test_api_telemetry_scoped_by_project(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a = c.get("/api/telemetry/summary", params={"project": "-proj-a"}).json()
    allp = c.get("/api/telemetry/summary", params={"project": "all"}).json()
    assert a["calls"] == 2
    assert allp["calls"] == 3
    assert a["scope"] == "-proj-a"
    assert allp["scope"] == "all projects"


def test_api_board_crud_roundtrip(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    eid = c.post("/api/epics", json={"title": "E"}).json()["id"]
    assert any(e["id"] == eid for e in c.get("/api/board").json()["epics"])
    assert c.patch(f"/api/epic/{eid}/status", json={"status": "done"}).json()["status"] == "done"
    assert c.delete(f"/api/epic/{eid}").json()["deleted"] == eid


# --- CLI link pulls REAL telemetry into a work_log ---
def test_cli_link_pulls_real_telemetry(monkeypatch, tmp_path):
    cd = _fake_claude(tmp_path)
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F"); st = s.add_story(f.id, "S")

    # NOTE: project slugs start with "-", so argparse needs the --opt=value form.
    rc = cli.main(["link", "--kind", "story", "--id", st.id,
                   "--session", "S1", "--project=-proj-a"])
    assert rc == 0
    reloaded = [x for x in BoardStore(board).load().stories if x.id == st.id][0]
    assert len(reloaded.work_log) == 1
    wl = reloaded.work_log[0]
    assert wl.input_tokens == 2000  # two S1 events x 1000
    assert wl.output_tokens == 1000
    assert wl.cost_usd > 0


def test_cli_link_no_match_errors(monkeypatch, tmp_path, capsys):
    cd = _fake_claude(tmp_path)
    board = tmp_path / "board.json"
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(cd))
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(board))
    s = BoardStore(board)
    e = s.add_epic("E"); f = s.add_feature(e.id, "F"); st = s.add_story(f.id, "S")
    rc = cli.main(["link", "--kind", "story", "--id", st.id, "--session", "NOPE",
                   "--project=-proj-a"])
    assert rc == 1
    assert "no telemetry matched" in capsys.readouterr().err
