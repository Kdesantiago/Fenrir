"""Cross-platform coverage for the tracking engine's launcher + the plugin-level auto-registered
hooks manifest.

`scripts/track_session.py::_dash_python` must find the dashboard venv interpreter on BOTH POSIX
(`.venv/bin/python`) and Windows (`.venv/Scripts/python.exe`), else fall back to sys.executable.

`hooks/hooks.json` (plugin root) auto-registers ONLY the fail-open tracking hooks via SHELL-form
(a single `command` string `"${CLAUDE_PLUGIN_ROOT}/hooks/run-python.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/*.py"`,
no `args`). run-python.sh probes python3 -> python -> py -3 so a Windows-safe interpreter resolves on
every OS (ADR 0004 replaced the old exec-form `python`+args, which had no cross-OS bare token).

Self-contained: track_session is loaded by file path (it lives outside the dashboard package),
the venv layouts are faked under tmp_path, and hooks.json is read from the repo on disk.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRACK_SESSION = _REPO_ROOT / "scripts" / "track_session.py"
_HOOKS_JSON = _REPO_ROOT / "hooks" / "hooks.json"
_TEMPLATE_SETTINGS = _REPO_ROOT / "templates" / ".claude" / "settings.json"


def _load_track_session():
    spec = importlib.util.spec_from_file_location("track_session_under_test", _TRACK_SESSION)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- _dash_python: both venv layouts + fallback ---------------------------------------


def test_dash_python_posix_venv_layout(tmp_path):
    ts = _load_track_session()
    dash = tmp_path / "dash"
    bin_py = dash / ".venv" / "bin" / "python"
    bin_py.parent.mkdir(parents=True)
    bin_py.write_text("#!/bin/sh\n")
    assert ts._dash_python(str(dash)) == str(bin_py)


def test_dash_python_windows_venv_layout(tmp_path):
    ts = _load_track_session()
    dash = tmp_path / "dash"
    win_py = dash / ".venv" / "Scripts" / "python.exe"
    win_py.parent.mkdir(parents=True)
    win_py.write_text("")
    assert ts._dash_python(str(dash)) == str(win_py)


def test_dash_python_falls_back_to_sys_executable(tmp_path):
    ts = _load_track_session()
    dash = tmp_path / "dash"
    dash.mkdir()
    assert ts._dash_python(str(dash)) == sys.executable


def test_dash_python_both_layouts_absent_returns_sys_executable(tmp_path):
    # A .venv dir exists but neither bin/python nor Scripts/python.exe is present -> the loop
    # finds nothing and must fall back to the current interpreter (no crash, no empty path).
    ts = _load_track_session()
    dash = tmp_path / "dash"
    (dash / ".venv").mkdir(parents=True)  # empty venv skeleton, no interpreter under it
    assert ts._dash_python(str(dash)) == sys.executable


def test_dash_python_ignores_directory_named_python(tmp_path):
    # A DIR (not a file) named `bin/python` must NOT be returned -- launching it as an interpreter
    # would crash the subprocess. isfile (not exists) means we fall back to sys.executable.
    ts = _load_track_session()
    dash = tmp_path / "dash"
    (dash / ".venv" / "bin" / "python").mkdir(parents=True)  # a directory, not an executable file
    assert ts._dash_python(str(dash)) == sys.executable


def test_dash_python_windows_only_layout_present_is_returned(tmp_path):
    # ONLY the Windows layout exists (no POSIX bin/python) -> the Windows interpreter is returned,
    # never the sys.executable fallback. Proves the loop reaches the Scripts/python.exe branch.
    ts = _load_track_session()
    dash = tmp_path / "dash"
    win_py = dash / ".venv" / "Scripts" / "python.exe"
    win_py.parent.mkdir(parents=True)
    win_py.write_text("")
    # the POSIX path deliberately does NOT exist
    assert not (dash / ".venv" / "bin" / "python").exists()
    result = ts._dash_python(str(dash))
    assert result == str(win_py)
    assert result != sys.executable


# --- hooks/hooks.json: valid JSON + expected events via shell-form ---------------------

_EXPECTED = {
    "UserPromptSubmit": ("tracking-open.py", None),
    "SubagentStop": ("tracking-collect.py", None),
    "PostToolUse": ("tracking-attribute.py", "Bash"),
    "Stop": ("tracking-finalize.py", None),
    "SessionEnd": ("tracking-finalize.py", None),
    "PreCompact": ("precompact-focus.py", None),
}

# The launcher every tracking entry must shell out to (ADR 0004); resolves the interpreter cross-OS.
_RUN_PYTHON_SH = "run-python.sh"


def _script_basename_from_command(command: str) -> str:
    """Extract the hook *.py* script basename from a shell-form command string.

    Shell form is a single string: `"<root>/hooks/run-python.sh" "<root>/hooks/<script>.py"`.
    The script is the last whitespace-separated token; strip the surrounding quotes and any
    directory prefix (POSIX `/` or Windows `\\`), so we never rely on a (now-absent) `args` key.
    """
    token = command.split()[-1].strip('"').strip("'")
    return token.replace("\\", "/").rsplit("/", 1)[-1]


def test_hooks_json_is_valid_json():
    json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))  # raises on malformed


def test_hooks_json_registers_expected_tracking_events():
    data = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    hooks = data["hooks"]
    assert set(hooks) == set(_EXPECTED)
    for event, (script, matcher) in _EXPECTED.items():
        groups = hooks[event]
        assert len(groups) == 1
        group = groups[0]
        assert group.get("matcher") == matcher  # Bash for PostToolUse, null otherwise
        cmds = group["hooks"]
        assert len(cmds) == 1
        cmd = cmds[0]
        # shell-form: a single `command` string routed through run-python.sh, NO `args` key.
        assert cmd["type"] == "command"
        assert "args" not in cmd, f"{event}: shell-form must not carry an args key"
        command = cmd["command"]
        assert isinstance(command, str)
        # both the launcher and the target script are addressed under ${CLAUDE_PLUGIN_ROOT}
        assert "${CLAUDE_PLUGIN_ROOT}" in command
        assert _RUN_PYTHON_SH in command
        # the registered event maps to the expected script, parsed out of the command string
        assert _script_basename_from_command(command) == script


def test_hooks_json_excludes_enforcement_hooks():
    # Only the fail-open TRACKING hooks auto-register; enforcement/guard hooks stay opt-in.
    raw = _HOOKS_JSON.read_text(encoding="utf-8")
    for enforcement in ("delivery-guard", "prompt-guard", "content-scanner", "config-audit",
                        "branch-plan-check", "tracking-guard", "iac-watch", "tool-failure-triage"):
        assert enforcement not in raw


@pytest.mark.parametrize("script", [s for s, _ in _EXPECTED.values()])
def test_referenced_hook_scripts_exist(script):
    assert (_REPO_ROOT / "hooks" / script).is_file()


# --- no double-fire: plugin-level hooks.json vs repo template settings.json -------------
# US4 intent: the tracking hooks register ONCE (at the plugin level, hooks.json). If the repo
# template ALSO carried them they would fire twice per event (double-count cost / double board
# churn). So none of the tracking script basenames registered in hooks.json may appear in the
# template, AND the enforcement/guard hooks (opt-in via repo-bootstrap) must still be there.

_ENFORCEMENT_HOOKS = (
    "delivery-guard", "prompt-guard", "content-scanner", "config-audit",
    "branch-plan-check", "tracking-guard", "iac-watch", "tool-failure-triage",
)


def _tracking_script_basenames() -> set[str]:
    """The tracking script basenames the plugin auto-registers.

    Shell-form entries carry no `args`; the script is parsed out of each `command` string
    (last quoted token under ${CLAUDE_PLUGIN_ROOT}), not from a `cmd["args"]` list.
    """
    data = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    names: set[str] = set()
    for groups in data["hooks"].values():
        for group in groups:
            for cmd in group["hooks"]:
                names.add(_script_basename_from_command(cmd["command"]))
    return names


def test_template_does_not_redeclare_tracking_hooks():
    # No tracking script auto-registered by the plugin may also live in the template -> no double-fire.
    raw = _TEMPLATE_SETTINGS.read_text(encoding="utf-8")
    tracking = _tracking_script_basenames()
    assert tracking, "hooks.json registered no tracking scripts (manifest regressed?)"
    leaked = sorted(name for name in tracking if name in raw)
    assert leaked == [], f"tracking hooks still in template (would double-fire): {leaked}"


def test_template_still_registers_enforcement_hooks():
    # The enforcement/guard layer stays opt-in via the repo template -> must remain present.
    raw = _TEMPLATE_SETTINGS.read_text(encoding="utf-8")
    missing = sorted(h for h in _ENFORCEMENT_HOOKS if f"{h}.py" not in raw)
    assert missing == [], f"enforcement hooks missing from template: {missing}"


def test_template_settings_is_valid_json():
    json.loads(_TEMPLATE_SETTINGS.read_text(encoding="utf-8"))  # raises on malformed


def test_hooks_json_every_registered_hook_invokes_run_python_launcher():
    # Every hook in the plugin manifest must use SHELL form (ADR 0004): a single `command` STRING
    # that routes the *.py script through run-python.sh, so a Windows-safe interpreter is probed at
    # runtime (no bare `python`/`python3` token, which resolves on no single OS by default). The old
    # exec-form (`command=="python"` + args) is gone; assert the shipped shell-form design here.
    data = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    seen = 0
    for event, groups in data["hooks"].items():
        for group in groups:
            for cmd in group["hooks"]:
                seen += 1
                assert cmd["type"] == "command", f"{event}: not a command hook"
                assert "args" not in cmd, f"{event}: shell-form must carry no args key, got {cmd!r}"
                command = cmd.get("command")
                assert isinstance(command, str) and command, (
                    f"{event}: shell-form needs a command string, got {command!r}")
                # routed through the committed POSIX launcher, not a bare interpreter token
                assert _RUN_PYTHON_SH in command, (
                    f"{event}: command must invoke run-python.sh, got {command!r}")
                # both the launcher and the script are substituted under ${CLAUDE_PLUGIN_ROOT}
                assert "${CLAUDE_PLUGIN_ROOT}" in command, (
                    f"{event}: command must reference ${{CLAUDE_PLUGIN_ROOT}}, got {command!r}")
                # no bare interpreter token may be smuggled into the command (Windows has no `python3`)
                for bare in ("python3 ", "python "):
                    assert bare not in command, (
                        f"{event}: bare interpreter token {bare!r} must not appear, got {command!r}")
                # the command actually addresses a tracking *.py script via the launcher
                assert _script_basename_from_command(command).endswith(".py"), (
                    f"{event}: command must target a .py script, got {command!r}")
    assert seen >= 6  # 6 event registrations (Stop + SessionEnd both -> finalize)
