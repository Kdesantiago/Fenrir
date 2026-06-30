"""PF1 regression: when the bundled-backend launcher runs, project/board resolution must key off
`CLAUDE_PROJECT_DIR` (the user's repo, exported by scripts/dashboard.py) — NOT the process cwd
(which is <plugin>/dashboard and would mis-resolve to the plugin's own board).

Contract under test (telemetry.resolution_base):
  explicit `cwd` arg  >  CLAUDE_PROJECT_DIR (set+non-empty)  >  Path.cwd()

The env branch is gated on the var being non-empty, so run-from-repo dev mode and every existing
cwd-based test are unchanged when it is absent. Self-contained: a fake ~/.claude under tmp_path,
`_git_root` monkeypatched so no real git is needed.
"""
from __future__ import annotations

from pathlib import Path

from backend import config, telemetry


def _mk_project(claude_dir: Path, slug: str) -> Path:
    p = claude_dir / "projects" / slug
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- resolution_base: the new chokepoint ----------------------------------------------


def test_resolution_base_prefers_explicit_cwd(monkeypatch, tmp_path):
    # An explicit cwd arg always wins, even with the env set (tests rely on this).
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "env_repo"))
    assert telemetry.resolution_base(tmp_path / "explicit") == tmp_path / "explicit"


def test_resolution_base_uses_env_when_no_cwd(monkeypatch, tmp_path):
    repo = tmp_path / "user_repo"
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    assert telemetry.resolution_base() == repo


def test_resolution_base_falls_back_to_cwd_when_env_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert telemetry.resolution_base() == Path.cwd()


def test_resolution_base_ignores_empty_env(monkeypatch, tmp_path):
    # Empty/whitespace var must NOT shadow the cwd fallback.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "   ")
    monkeypatch.chdir(tmp_path)
    assert telemetry.resolution_base() == Path.cwd()


# --- current_project_slug routes through resolution_base ------------------------------


def test_slug_keys_off_claude_project_dir_not_cwd(monkeypatch, tmp_path):
    """The crux: cwd is the (plugin) dashboard dir, but CLAUDE_PROJECT_DIR is the user repo —
    the slug must be the USER repo's, not the cwd's."""
    user_repo = tmp_path / "user_repo"
    plugin_dash = tmp_path / "plugin" / "dashboard"
    user_repo.mkdir(parents=True)
    plugin_dash.mkdir(parents=True)

    user_slug = telemetry.encode_project(user_repo)
    plugin_slug = telemetry.encode_project(plugin_dash)

    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, user_slug)
    _mk_project(claude_dir, plugin_slug)  # the plugin's own project must NOT win

    # git root == the dir itself for both (no real git); cwd is the plugin dash dir.
    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: cwd)
    monkeypatch.chdir(plugin_dash)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(user_repo))

    assert telemetry.current_project_slug(claude_dir) == user_slug


def test_slug_falls_back_to_cwd_without_env(monkeypatch, tmp_path):
    plugin_dash = tmp_path / "plugin" / "dashboard"
    plugin_dash.mkdir(parents=True)
    plugin_slug = telemetry.encode_project(plugin_dash)

    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, plugin_slug)

    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: cwd)
    monkeypatch.chdir(plugin_dash)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    assert telemetry.current_project_slug(claude_dir) == plugin_slug


# --- board_path: reader + writer agree on the SAME file -------------------------------


def test_board_path_keys_off_claude_project_dir(monkeypatch, tmp_path):
    user_repo = tmp_path / "user_repo"
    plugin_dash = tmp_path / "plugin" / "dashboard"
    user_repo.mkdir(parents=True)
    plugin_dash.mkdir(parents=True)
    user_slug = telemetry.encode_project(user_repo)

    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, user_slug)

    data = tmp_path / "data"
    monkeypatch.setattr(config, "_DATA", data)
    monkeypatch.setenv("FENRIR_DASH_CLAUDE_DIR", str(claude_dir))
    monkeypatch.delenv("FENRIR_DASH_BOARD", raising=False)
    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: cwd)
    monkeypatch.chdir(plugin_dash)  # cwd = plugin dashboard, as the launcher runs it
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(user_repo))

    # Board carries the USER repo's slug, not the plugin dash dir's.
    assert config.board_path() == data / "boards" / f"{user_slug}.json"


def test_fenrir_dash_board_still_wins_over_claude_project_dir(monkeypatch, tmp_path):
    # The explicit pin keeps precedence over the new env branch.
    pinned = tmp_path / "pinned.json"
    monkeypatch.setattr(config, "_DATA", tmp_path)
    monkeypatch.setenv("FENRIR_DASH_BOARD", str(pinned))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "whatever"))
    assert config.store().path == pinned
