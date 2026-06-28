"""Tests for the slug-resolution fix in backend.telemetry.current_project_slug.

`current_project_slug(claude_dir, cwd)` now resolves `cwd` to its **git repo root**
(`_git_root`) BEFORE encoding + matching, so a subdir (e.g. `<repo>/dashboard`) maps to
the repo's project — NOT a phantom `<repo>-dashboard` project an accidental subdir
invocation may have created in ~/.claude/projects. It then still picks the longest
available slug that prefixes the (root-resolved) encoding.

Cases 1+2 monkeypatch `telemetry._git_root` so they're deterministic with no real git.
Case 3 exercises `_git_root` itself against a real temp git repo (skipped if git absent).
Self-contained; only touches a fake ~/.claude under tmp_path.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from backend import telemetry


def _mk_project(claude_dir, slug: str):
    """Create projects/<slug>/ under a fake claude_dir."""
    p = claude_dir / "projects" / slug
    p.mkdir(parents=True)
    return p


# --- 1. subdir -> repo project (git root resolves) ------------------------------------


def test_subdir_resolves_to_repo_not_phantom(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    subdir = repo / "dashboard"
    subdir.mkdir(parents=True)

    repo_slug = telemetry.encode_project(repo)            # e.g. -..-repo
    phantom_slug = telemetry.encode_project(subdir)       # e.g. -..-repo-dashboard

    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, repo_slug)
    _mk_project(claude_dir, phantom_slug)  # the phantom must NOT win

    # git root of the subdir is the repo root -> encoding is the repo, not the subdir.
    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: repo)

    got = telemetry.current_project_slug(claude_dir, subdir)
    assert got == repo_slug, f"expected repo slug, got phantom-or-none: {got!r}"
    assert got != phantom_slug


def test_subdir_resolution_independent_of_phantom_existing(tmp_path, monkeypatch):
    # Even with ONLY the repo project present, a subdir cwd still resolves to it.
    repo = tmp_path / "repo"
    subdir = repo / "dashboard" / "backend"
    subdir.mkdir(parents=True)
    repo_slug = telemetry.encode_project(repo)

    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, repo_slug)

    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: repo)
    assert telemetry.current_project_slug(claude_dir, subdir) == repo_slug


# --- 2. non-git / _git_root None -> fall back to encoding cwd (prior behavior) --------


def test_non_git_falls_back_to_cwd_longest_prefix(tmp_path, monkeypatch):
    # _git_root None -> encode cwd directly; longest-prefix match still applies.
    repo = tmp_path / "repo"
    subdir = repo / "dashboard"
    subdir.mkdir(parents=True)

    repo_slug = telemetry.encode_project(repo)
    sub_slug = telemetry.encode_project(subdir)  # the longer slug that prefixes the cwd enc

    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, repo_slug)
    _mk_project(claude_dir, sub_slug)

    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: None)

    # cwd encoding == sub_slug; both repo_slug and sub_slug prefix it -> longest wins.
    got = telemetry.current_project_slug(claude_dir, subdir)
    assert got == sub_slug


def test_non_git_subdir_matches_parent_when_only_parent_present(tmp_path, monkeypatch):
    # No git, only the parent slug present: cwd enc starts with parent slug -> parent.
    repo = tmp_path / "repo"
    deep = repo / "a" / "b"
    deep.mkdir(parents=True)
    repo_slug = telemetry.encode_project(repo)

    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, repo_slug)

    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: None)
    assert telemetry.current_project_slug(claude_dir, deep) == repo_slug


# --- 3. _git_root itself (real temp git repo) -----------------------------------------

_GIT = shutil.which("git")


@pytest.mark.skipif(_GIT is None, reason="git not available")
def test_git_root_returns_repo_toplevel(tmp_path):
    repo = tmp_path / "realrepo"
    sub = repo / "pkg" / "mod"
    sub.mkdir(parents=True)
    subprocess.run(["git", "init", str(repo)], check=True,
                   capture_output=True, text=True)

    got = telemetry._git_root(sub)
    assert got is not None
    # resolve() both sides: macOS /tmp is a symlink to /private/tmp.
    assert got.resolve() == repo.resolve()


@pytest.mark.skipif(_GIT is None, reason="git not available")
def test_git_root_none_outside_repo(tmp_path):
    nogit = tmp_path / "plain"
    nogit.mkdir()
    assert telemetry._git_root(nogit) is None


# --- 4. no project match -> None (unchanged) ------------------------------------------


def test_no_match_returns_none(tmp_path, monkeypatch):
    claude_dir = tmp_path / "fake_claude"
    _mk_project(claude_dir, "-some-unrelated-project")

    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: None)
    assert telemetry.current_project_slug(claude_dir, tmp_path / "elsewhere") is None


def test_no_projects_dir_returns_none(tmp_path, monkeypatch):
    # claude_dir has no projects/ at all.
    monkeypatch.setattr(telemetry, "_git_root", lambda cwd: None)
    assert telemetry.current_project_slug(tmp_path / "empty", tmp_path / "x") is None
