"""Tests for the Fenrir FileChanged hook: hooks/iac-watch.py.

The hook is NON-BLOCKING: it always exits 0 and never emits a permission
decision. Its observable contract is:
  - exit code is ALWAYS 0 (empty/malformed stdin, missing file, any extension);
  - on a YAML file that fails to parse it prints a single
    "iac-watch: <path> has a YAML error: ..." line to stdout;
  - on a non-fmt-clean .tf file (only if `terraform` is installed) it prints
    "iac-watch: <path> is not terraform-fmt clean ...";
  - otherwise it prints nothing.

These tests are subprocess-based and validated against the real hook's
observed behavior. stdlib + pytest only; fully self-contained (no conftest,
no __init__).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "iac-watch.py"

HAS_TERRAFORM = shutil.which("terraform") is not None
HAS_YAML = False
try:  # the hook degrades silently without PyYAML; tests do too
    import yaml  # noqa: F401

    HAS_YAML = True
except ImportError:
    pass


def run_hook(stdin_text, project_dir):
    """Invoke the real hook with `stdin_text` piped in, isolated to project_dir."""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env={"CLAUDE_PROJECT_DIR": str(project_dir), "PATH": _path_env()},
    )


def _path_env():
    import os

    return os.environ.get("PATH", "")


def payload(file_path):
    return json.dumps({"file_path": str(file_path)})


# --- always-exit-0 / no-op paths -------------------------------------------

@pytest.mark.parametrize(
    "stdin_text",
    [
        "",                       # empty stdin
        "not json at all",        # malformed json
        "{",                      # truncated json
        "{}",                     # valid json, no file_path
        '{"file_path": ""}',      # empty file_path
        '{"file_path": null}',    # null file_path
        '{"file_path": "/no/such/path/main.tf"}',  # nonexistent file
        '{"file_path": "/no/such/path/x.yaml"}',   # nonexistent yaml
    ],
)
def test_noop_paths_exit_zero_no_output(stdin_text, tmp_path):
    r = run_hook(stdin_text, tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


def test_unwatched_extension_is_noop(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello\n")
    r = run_hook(payload(f), tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


# --- YAML validation path (the hook's primary "print" path) -----------------

@pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed; hook no-ops")
@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_valid_yaml_is_silent(tmp_path, suffix):
    f = tmp_path / ("good" + suffix)
    f.write_text("a: 1\nb:\n  - x\n  - y\n")
    r = run_hook(payload(f), tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


@pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed; hook no-ops")
def test_yaml_comment_only_is_silent(tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text("# just a comment, parses to None\n")
    r = run_hook(payload(f), tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


@pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed; hook no-ops")
@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_invalid_yaml_prints_error_but_exits_zero(tmp_path, suffix):
    f = tmp_path / ("bad" + suffix)
    # mapping value in a bad position -> yaml.safe_load_all raises
    f.write_text("a: 1\n  b: : :\n - x\n")
    r = run_hook(payload(f), tmp_path)
    # NON-BLOCKING: still exit 0 even though the content is broken.
    assert r.returncode == 0
    assert r.stdout.startswith(f"iac-watch: {f} has a YAML error:")


@pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed; hook no-ops")
def test_yaml_error_message_is_truncated(tmp_path):
    """The hook slices the exception text to 160 chars (str(e)[:160])."""
    f = tmp_path / "bad.yaml"
    f.write_text("a: 1\n  b: : :\n")
    r = run_hook(payload(f), tmp_path)
    assert r.returncode == 0
    prefix = f"iac-watch: {f} has a YAML error: "
    assert r.stdout.startswith(prefix)
    detail = r.stdout[len(prefix):].rstrip("\n")
    assert len(detail) <= 160


@pytest.mark.skipif(HAS_YAML, reason="PyYAML present; ImportError path not exercised")
def test_invalid_yaml_silent_when_pyyaml_absent(tmp_path):
    """Without PyYAML the hook swallows ImportError and stays silent."""
    f = tmp_path / "bad.yaml"
    f.write_text("a: 1\n  b: : :\n")
    r = run_hook(payload(f), tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""


# --- terraform path ---------------------------------------------------------

def test_tf_file_exits_zero(tmp_path):
    """A .tf file: exit 0 regardless. If terraform is absent the hook swallows
    FileNotFoundError and prints nothing; if present and the file is not
    fmt-clean it prints a one-liner. Either way the exit code is 0."""
    f = tmp_path / "main.tf"
    # intentionally not fmt-clean (extra spaces / no canonical formatting)
    f.write_text('resource    "null_resource"  "x" {\n count=1\n}\n')
    r = run_hook(payload(f), tmp_path)
    assert r.returncode == 0
    if not HAS_TERRAFORM:
        assert r.stdout == ""


@pytest.mark.skipif(not HAS_TERRAFORM, reason="terraform not installed")
def test_tf_not_fmt_clean_prints_hint(tmp_path):
    f = tmp_path / "main.tf"
    f.write_text('resource    "null_resource"  "x" {\n count=1\n}\n')
    r = run_hook(payload(f), tmp_path)
    assert r.returncode == 0
    assert "is not terraform-fmt clean" in r.stdout


def test_no_side_effect_files_written(tmp_path):
    """The hook must not create audit logs or any files in the project dir."""
    f = tmp_path / "bad.yaml"
    f.write_text("a: 1\n  b: : :\n")
    before = {p.name for p in tmp_path.iterdir()}
    run_hook(payload(f), tmp_path)
    after = {p.name for p in tmp_path.iterdir()}
    assert before == after
