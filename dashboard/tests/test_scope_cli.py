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


# The fake claude tree mirrors REAL slugs, which differ per OS (Windows lowercases the drive
# and turns `\` `:` into `-`). Derive them from encode_project so the asserts are OS-independent
# instead of hard-coding the POSIX form (which would not match on Windows).
PROJ_A = telemetry.encode_project(Path("/proj/a"))
PROJ_B = telemetry.encode_project(Path("/proj/b"))


def _fake_claude(tmp: Path) -> Path:
    cd = tmp / "claude"
    (cd / "projects" / PROJ_A).mkdir(parents=True)
    (cd / "projects" / PROJ_B).mkdir(parents=True)
    (cd / "projects" / PROJ_A / "s1.jsonl").write_text(_ev("S1") + "\n" + _ev("S1") + "\n")
    (cd / "projects" / PROJ_B / "s2.jsonl").write_text(_ev("S2") + "\n")
    return cd


# --- telemetry helpers ---
def test_encode_project():
    # POSIX path: no drive/backslash/colon -> only `/` and `.` collapse to `-` (byte-identical
    # to the historical behavior, so Linux CI is unchanged).
    assert telemetry.encode_project(Path("/a/b.c")).endswith("-a-b-c")
    # Windows convention: drive letter lowercased, `\` and `:` -> `-`. Apply the same rule the
    # function uses so the expectation holds on whatever OS resolves the path.
    win = telemetry.encode_project(Path(r"C:\Users\me\repo"))
    assert "Users-me-repo" in win
    assert ":" not in win and "\\" not in win and "/" not in win


def test_list_projects(tmp_path):
    cd = _fake_claude(tmp_path)
    assert telemetry.list_projects(cd) == sorted([PROJ_A, PROJ_B])


def test_current_project_slug_prefix_match(tmp_path):
    cd = _fake_claude(tmp_path)
    # a cwd inside proj/a (its encoding has PROJ_A as a prefix) resolves to PROJ_A
    sub = Path("/proj/a/sub")
    assert telemetry.encode_project(sub).startswith(PROJ_A)
    assert telemetry.current_project_slug(cd, sub) == PROJ_A
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
    assert set(body["projects"]) == {PROJ_A, PROJ_B}


def test_api_telemetry_scoped_by_project(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    a = c.get("/api/telemetry/summary", params={"project": PROJ_A}).json()
    allp = c.get("/api/telemetry/summary", params={"project": "all"}).json()
    assert a["calls"] == 2
    assert allp["calls"] == 3
    assert a["scope"] == PROJ_A
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

    # NOTE: POSIX project slugs start with "-", so argparse needs the --opt=value form.
    rc = cli.main(["link", "--kind", "story", "--id", st.id,
                   "--session", "S1", f"--project={PROJ_A}"])
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
                   f"--project={PROJ_A}"])
    assert rc == 1
    assert "no telemetry matched" in capsys.readouterr().err
