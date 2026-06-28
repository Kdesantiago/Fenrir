"""Tests for the self-documenting catalog (backend.catalog). Builds an ISOLATED fake plugin tree
on tmp_path and points FENRIR_PLUGIN_ROOT at it via monkeypatch — never touches the real repo.
Covers frontmatter parsing per kind, the namespaced command name, hook event/matcher wiring from
.claude/settings.json, counts, and fail-soft on an empty/missing tree."""
from __future__ import annotations

import json

from backend import catalog


def _write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _root(monkeypatch, tmp_path):
    monkeypatch.setenv("FENRIR_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return tmp_path


# 1. agents -------------------------------------------------------------------

def test_agent_frontmatter_parsed_into_fields(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "agents" / "foo.md",
           "---\nname: foo-agent\ndescription: Does the foo\ntools: Read, Bash\nmodel: opus\n---\nbody\n")
    agents = catalog.catalog()["agents"]
    assert agents == [{"name": "foo-agent", "description": "Does the foo",
                       "tools": "Read, Bash", "model": "opus"}]


def test_agent_name_falls_back_to_filename_stem(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "agents" / "bar.md", "---\ndescription: no name key\n---\n")
    agents = catalog.catalog()["agents"]
    assert agents[0]["name"] == "bar"
    assert agents[0]["description"] == "no name key"


# 2. skills -------------------------------------------------------------------

def test_skill_frontmatter_one_entry(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "skills" / "bar" / "SKILL.md",
           "---\nname: bar-skill\ndescription: A bar skill\n---\n")
    skills = catalog.catalog()["skills"]
    assert skills == [{"name": "bar-skill", "description": "A bar skill"}]


def test_skill_name_falls_back_to_dir_name(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "skills" / "scoped" / "SKILL.md", "---\ndescription: unnamed\n---\n")
    skills = catalog.catalog()["skills"]
    assert skills[0]["name"] == "scoped"


# 3. commands -----------------------------------------------------------------

def test_command_name_is_namespaced_from_filename(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "commands" / "plan.md", "---\ndescription: Plan the work\n---\n")
    commands = catalog.catalog()["commands"]
    assert commands == [{"name": "fenrir:plan", "description": "Plan the work"}]


# 4. hooks + event mapping ----------------------------------------------------

def test_hook_wired_with_events_and_matchers(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "hooks" / "x.py", '"""First line desc.\n\nmore detail.\n"""\nprint("hi")\n')
    settings = {"hooks": {"PostToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "python hooks/x.py"}]}]}}
    _write(root / ".claude" / "settings.json", json.dumps(settings))
    hooks = catalog.catalog()["hooks"]
    assert hooks == [{"name": "x.py", "description": "First line desc.",
                      "events": ["PostToolUse"], "matchers": ["Bash"], "wired": True}]


def test_hook_present_but_unwired(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "hooks" / "lonely.py", '"""I fire on nothing."""\n')
    _write(root / ".claude" / "settings.json", json.dumps({"hooks": {}}))
    hooks = catalog.catalog()["hooks"]
    assert hooks == [{"name": "lonely.py", "description": "I fire on nothing.",
                      "events": [], "matchers": [], "wired": False}]


def test_hook_unwired_when_settings_missing(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "hooks" / "orphan.py", '"""Orphan hook."""\n')  # no .claude/settings.json
    hooks = catalog.catalog()["hooks"]
    assert hooks == [{"name": "orphan.py", "description": "Orphan hook.",
                      "events": [], "matchers": [], "wired": False}]


def test_hook_events_deduped_and_sorted_across_blocks(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "hooks" / "multi.py", '"""Multi-event hook."""\n')
    settings = {"hooks": {
        "PreToolUse": [{"matcher": "Write", "hooks": [{"command": "hooks/multi.py"}]}],
        "PostToolUse": [
            {"matcher": "Bash", "hooks": [{"command": "hooks/multi.py"}]},
            {"matcher": "Write", "hooks": [{"command": "hooks/multi.py"}]}]}}
    _write(root / ".claude" / "settings.json", json.dumps(settings))
    hooks = catalog.catalog()["hooks"]
    assert hooks[0]["events"] == ["PostToolUse", "PreToolUse"]   # sorted, deduped
    assert hooks[0]["matchers"] == ["Bash", "Write"]            # sorted, deduped
    assert hooks[0]["wired"] is True


# 5. counts -------------------------------------------------------------------

def test_counts_match_lengths(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "agents" / "a1.md", "---\nname: a1\ndescription: d\n---\n")
    _write(root / "agents" / "a2.md", "---\nname: a2\ndescription: d\n---\n")
    _write(root / "skills" / "s1" / "SKILL.md", "---\nname: s1\ndescription: d\n---\n")
    _write(root / "commands" / "c1.md", "---\ndescription: d\n---\n")
    _write(root / "hooks" / "h1.py", '"""h1."""\n')
    cat = catalog.catalog()
    assert cat["counts"] == {"agents": 2, "skills": 1, "commands": 1, "hooks": 1}
    assert cat["counts"] == {k: len(cat[k]) for k in ("agents", "skills", "commands", "hooks")}


# 6. fail-soft ----------------------------------------------------------------

def test_empty_tree_yields_empty_lists_and_zero_counts(monkeypatch, tmp_path):
    _root(monkeypatch, tmp_path)  # tmp_path exists but has no agents/skills/commands/hooks dirs
    cat = catalog.catalog()
    assert cat["agents"] == [] and cat["skills"] == []
    assert cat["commands"] == [] and cat["hooks"] == []
    assert cat["counts"] == {"agents": 0, "skills": 0, "commands": 0, "hooks": 0}


def test_malformed_settings_json_does_not_raise(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    _write(root / "hooks" / "h.py", '"""desc."""\n')
    _write(root / ".claude" / "settings.json", "{ not valid json ")
    hooks = catalog.catalog()["hooks"]   # must not raise
    assert hooks[0]["wired"] is False and hooks[0]["events"] == []


# 7. plugin-root resolution (red-team regression guards) ----------------------

def test_stray_claude_project_dir_is_ignored(monkeypatch, tmp_path):
    # CLAUDE_PROJECT_DIR is the USER's repo, NOT the plugin — it must not redirect the catalog.
    plugin, foreign = tmp_path / "plugin", tmp_path / "foreign"
    _write(plugin / "agents" / "real.md", "---\nname: real\ndescription: ours\n---\n")
    _write(foreign / "agents" / "ghost.md", "---\nname: ghost\ndescription: not ours\n---\n")
    monkeypatch.setenv("FENRIR_PLUGIN_ROOT", str(plugin))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(foreign))  # stray — must be ignored
    names = [a["name"] for a in catalog.catalog()["agents"]]
    assert names == ["real"] and "ghost" not in names


def test_last_py_token_is_the_hook(monkeypatch, tmp_path):
    # a wrapper invocation (`python runner.py hooks/x.py`) maps to the LAST .py, not the runner
    root = _root(monkeypatch, tmp_path)
    _write(root / "hooks" / "x.py", '"""the real hook."""\n')
    _write(root / ".claude" / "settings.json", json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "python3 runner.py $DIR/hooks/x.py"}]}]}}))
    hook = catalog.catalog()["hooks"][0]
    assert hook["name"] == "x.py" and hook["wired"] is True and hook["events"] == ["Stop"]
