"""The kanban board is per-project: data/boards/<slug>.json, isolated between projects."""
from backend import config


def test_board_path_per_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_DATA", tmp_path)
    monkeypatch.delenv("FENRIR_DASH_BOARD", raising=False)
    assert config.board_path("-projA") == tmp_path / "boards" / "-projA.json"


def test_boards_are_isolated_between_projects(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_DATA", tmp_path)
    monkeypatch.delenv("FENRIR_DASH_BOARD", raising=False)
    config.store("-projA").add_epic("A-only")
    config.store("-projB").add_epic("B-only")
    assert [e.title for e in config.store("-projA").load().epics] == ["A-only"]
    assert [e.title for e in config.store("-projB").load().epics] == ["B-only"]


def test_explicit_board_env_overrides_project(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_DATA", tmp_path)
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(tmp_path / "pinned.json"))
    # env wins regardless of the project arg
    assert config.store("-anything").path == tmp_path / "pinned.json"
