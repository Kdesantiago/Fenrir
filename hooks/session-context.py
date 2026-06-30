#!/usr/bin/env python3
"""fenrir — SessionStart context injector (delivery-memory).

Injects the ACTIVE delivery contract into every session so the rules are always-on:
declared stack (org-profile.yaml), enterprise wrappers (stack-interface.yaml, if any),
and open gate-exceptions from the in-repo delivery-memory. Pure stdlib.

Uses yaml.safe_load when PyYAML is available; otherwise a careful flat parser that
respects quotes and skips nested/list/empty values (so it never injects a half-read key).

Contract (SessionStart): print JSON, exit 0.
  {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":...}}
Fail-OPEN: nothing to inject → exit 0 silent.
"""
import json
import os
import sys
from datetime import date, datetime


def _root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _strip_comment(s):
    """Remove a # comment that is OUTSIDE quotes."""
    out, q = [], None
    for ch in s:
        if q:
            out.append(ch)
            if ch == q:
                q = None
        elif ch in ("'", '"'):
            q = ch; out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out)


def _flat_yaml(path):
    """Top-level `key: value` only. Skips indented (nested/list) lines and empty values."""
    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return {k: v for k, v in data.items() if isinstance(v, (str, int, float)) and str(v).strip()}
    except ImportError:
        pass
    except Exception:
        return {}
    out = {}
    try:
        for line in open(path):
            if not line.strip() or line.startswith((" ", "\t", "-", "#")):
                continue
            line = _strip_comment(line).rstrip()
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            v = v.strip().strip('"').strip("'")
            if v:  # skip empty/nested-parent keys
                out[k.strip()] = v
    except Exception:
        return {}
    return out


def _compact_focus(root):
    """The dev-subject snapshot written by precompact-focus.py before a compaction. Returned to
    re-seed a session that was JUST compacted, so the post-compaction context is about the work in
    progress (active US goal/acceptance, branch, in-flight files), not a flat global recap.
    '' if absent/unreadable."""
    fp = os.path.join(root, ".claude", "tracking", "compact-focus.md")
    try:
        with open(fp) as f:
            return f.read().strip()
    except Exception:
        return ""


def _open_exceptions(root):
    fp = os.path.join(root, "docs", "delivery-memory", "gate-exceptions.jsonl")
    today = date.today()
    rows = []
    try:
        for line in open(fp):
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            if e.get("status", "open") != "open":
                continue
            exp = e.get("expires")
            # Missing/unparseable/non-ISO expiry → treat as EXPIRED (closed), never open.
            try:
                if not exp or datetime.strptime(str(exp), "%Y-%m-%d").date() < today:
                    continue
            except (ValueError, TypeError):
                continue
            rows.append(e)
    except FileNotFoundError:
        pass
    except Exception:
        return []
    return rows


def main():
    root = _root()
    try:
        source = (json.load(sys.stdin) or {}).get("source", "")
    except Exception:
        source = ""
    parts = []

    # Just compacted? Lead with the dev-subject snapshot so the model re-grounds on the work in
    # progress (PreCompact can't steer the summary; this re-injects the focus right after).
    focus = _compact_focus(root) if source == "compact" else ""
    if focus:
        parts.append("RESUMING AFTER COMPACTION — focus on the active development below; treat "
                     "unrelated history as compressed:\n" + focus)

    prof = _flat_yaml(os.path.join(root, "org-profile.yaml"))
    if prof:
        keys = ["platform", "framework", "auth_provider", "obs_backend", "llm_provider", "front", "template_version"]
        decl = ", ".join(f"{k}={prof[k]}" for k in keys if k in prof)
        if decl:
            parts.append(f"DELIVERY CONTRACT (org-profile.yaml): {decl}. Generators must match this stack or refuse.")

    si_path = os.path.join(root, "stack-interface.yaml")
    if os.path.exists(si_path):
        si = _flat_yaml(si_path)
        wrappers = ", ".join(f"{k}={si[k]}" for k in si if k not in ("name", "version"))
        if wrappers:
            parts.append(f"STACK INTERFACE active: use the declared wrappers, not raw cloud CLIs ({wrappers}). Delegate stack ops to the stack-adapter agent.")

    exc = _open_exceptions(root)
    if exc:
        lines = "; ".join(f"{e.get('rule','?')} (until {e.get('expires','?')}, by {e.get('granted_by','?')})" for e in exc[:8])
        parts.append(f"OPEN GATE-EXCEPTIONS ({len(exc)}): {lines}. Temporary waivers — prefer fixing the underlying issue.")

    if not parts:
        sys.exit(0)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
        "additionalContext": "\n".join("• " + p for p in parts)}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
