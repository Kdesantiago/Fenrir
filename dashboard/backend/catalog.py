"""Self-documenting catalog: reads the Fenrir plugin's own agents / hooks / skills / commands
from disk so the dashboard can show what each one is — name + description (+ for hooks, the
event it fires on; for agents, its tools). Pure stdlib, read-only, fail-soft (a missing dir or
unreadable file is skipped, never raised). Lets a newcomer understand the pack with zero code
reading. The plugin root is the repo root (this file lives at <root>/dashboard/backend/)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)
_DOC = re.compile(r'"""(.*?)"""', re.S)
_HOOK_FILE = re.compile(r"([\w-]+\.py)")


def _plugin_root() -> Path:
    """The PLUGIN's root (where agents/hooks/skills/commands live) = the dir containing this
    dashboard, i.e. <root>/dashboard/backend → <root>. NOTE: deliberately does NOT fall back to
    CLAUDE_PROJECT_DIR — that var is the *user's in-session repo* (see config.py), a different
    directory; trusting it would make the catalog document the wrong repo (empty, or the user's
    own files). Only an explicit FENRIR_PLUGIN_ROOT overrides (e.g. an unusual install layout)."""
    p = os.environ.get("FENRIR_PLUGIN_ROOT")
    if p and Path(p).is_dir():
        return Path(p)
    return Path(__file__).resolve().parents[2]


def _frontmatter(text: str) -> dict:
    """Top-level `key: value` from a YAML frontmatter block (single-line values; long descriptions
    are one line in these files). Skips nested/list lines so a multi-line value never half-reads."""
    m = _FM.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-", "#")):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _read(f: Path) -> str:
    try:
        return f.read_text(errors="ignore")
    except OSError:
        return ""


def _agents(root: Path) -> list[dict]:
    d = root / "agents"
    out = []
    if d.is_dir():
        for f in sorted(d.glob("*.md")):
            fm = _frontmatter(_read(f))
            out.append({"name": fm.get("name") or f.stem, "description": fm.get("description", ""),
                        "tools": fm.get("tools", ""), "model": fm.get("model", "")})
    return out


def _skills(root: Path) -> list[dict]:
    d = root / "skills"
    out = []
    if d.is_dir():
        for f in sorted(d.glob("*/SKILL.md")):
            fm = _frontmatter(_read(f))
            out.append({"name": fm.get("name") or f.parent.name, "description": fm.get("description", "")})
    return out


def _commands(root: Path) -> list[dict]:
    d = root / "commands"
    out = []
    if d.is_dir():
        for f in sorted(d.glob("*.md")):
            fm = _frontmatter(_read(f))
            # invocation is always the namespaced form
            out.append({"name": f"fenrir:{f.stem}", "description": fm.get("description", "")})
    return out


def _hook_events(root: Path) -> dict[str, list[tuple[str, str]]]:
    """Map `<hook>.py` → [(event, matcher), …] from .claude/settings.json (so the catalog can say
    WHEN each hook fires). Empty on any trouble."""
    ev: dict[str, list[tuple[str, str]]] = {}
    try:
        d = json.loads(_read(root / ".claude" / "settings.json"))
    except (ValueError, OSError):
        return ev
    for event, blocks in (d.get("hooks") or {}).items():
        for b in blocks if isinstance(blocks, list) else []:
            matcher = b.get("matcher", "") if isinstance(b, dict) else ""
            for h in (b.get("hooks", []) if isinstance(b, dict) else []):
                # the hook file is the LAST .py token in the command (`python3 ".../hooks/x.py"`,
                # or even a wrapper `python runner.py hooks/x.py`) — not the first (the runner).
                matches = _HOOK_FILE.findall(h.get("command", "") if isinstance(h, dict) else "")
                if matches:
                    ev.setdefault(matches[-1], []).append((event, matcher))
    return ev


def _hooks(root: Path) -> list[dict]:
    d = root / "hooks"
    out: list[dict] = []
    if not d.is_dir():
        return out
    wired = _hook_events(root)
    for f in sorted(d.glob("*.py")):
        m = _DOC.search(_read(f))
        desc = ""
        if m:
            # first non-empty line of the module docstring (often "fenrir — Event: summary")
            for line in m.group(1).strip().splitlines():
                if line.strip():
                    desc = line.strip()
                    break
        evs = wired.get(f.name, [])
        out.append({"name": f.name, "description": desc,
                    "events": sorted({e for e, _ in evs}),
                    "matchers": sorted({mm for _, mm in evs if mm}),
                    "wired": bool(evs)})
    return out


def catalog() -> dict:
    """The full self-documenting catalog, grouped by kind, with per-kind counts."""
    root = _plugin_root()
    data = {"agents": _agents(root), "skills": _skills(root),
            "commands": _commands(root), "hooks": _hooks(root)}
    return {**data, "counts": {k: len(v) for k, v in data.items()}}
