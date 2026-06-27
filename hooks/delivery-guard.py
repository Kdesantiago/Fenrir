#!/usr/bin/env python3
"""fenrir — PreToolUse guard (couche 0, in-session enforcement + security).

A skill cannot block anything. This hook can: Claude Code runs it BEFORE a tool
executes and honors its decision. In-session twin of the repo-side gate (pre-commit +
CI + branch-protection), plus a best-effort security surface ported from PAI inspectors
(Egress, Pattern) into pure Python stdlib — no bun/node/daemon.

IMPORTANT: regex command-scanning is a BEST-EFFORT control, not a sandbox. It raises the
cost of accidental/lazy bypass; a determined attacker with shell access can still evade.
The authoritative controls are the OS/CI (no secrets on disk, least privilege, branch
protection). This hook FAILS CLOSED for mutating tools (Bash/Write/Edit/MultiEdit/
NotebookEdit): a malformed/unparseable call is DENIED, not allowed.

Decision contract (PreToolUse): print JSON on stdout, exit 0. permissionDecision:
  deny | ask | allow. Denies/asks also append to .claude/audit/security-events.jsonl.
"""
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

I = re.IGNORECASE

# --- couche-0 gate files ---
# Editing the guard's own kill switch is DENIED; other gate files are ASK.
KILL_SWITCH = [r"(^|/)\.claude/hooks/", r"(^|/)\.claude/settings(\.local)?\.json$"]
PROTECTED_PATHS = [
    r"(^|/)branch-protection\.tf$", r"(^|/)azure-branch-policy\.tf$",
    r"(^|/)\.pre-commit-config\.yaml$", r"(^|/)org-profile\.yaml$",
    r"(^|/)stack-interface\.yaml$", r"(^|/)CODEOWNERS$", r"(^|/)\.semgrep\.yml$",
    r"(^|/)templates/ci/", r"(^|/)\.github/workflows/", r"(^|/)azure-pipelines?\.yml$",
]

# --- secret files: never read/move/write via any tool (excludes .env.example etc.) ---
SECRET_FILE = re.compile(
    r"(^|/|\s|['\"<])(\.env(?!\.(?:example|sample|template|dist)\b)(?:\.[a-z]+)?|\.ssh/|id_rsa|id_ed25519|"
    r"\.aws/credentials|[\w./-]+\.pem|secrets?\.ya?ml|\.npmrc|\.pypirc)\b", I)

# --- secret token shapes (literal-in-command; weak against indirection, hence the broader rules below) ---
SECRET_TOKENS = re.compile(
    r"(sk_live_|sk_test_|sk-ant-|sk-proj-|whsec_|ghp_[A-Za-z0-9]{20,}|github_pat_|AKIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_\-]{20,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|sig=[A-Za-z0-9%]{20,})", I)
SECRET_ENV = re.compile(r"\$[\{(]?[A-Z_]*(TOKEN|SECRET|KEY|PASSWORD|PASSWD|CRED|API)[A-Z_]*", I)
OUTBOUND = re.compile(r"\b(curl|wget|nc|ncat|socat|scp|rsync|gsutil|telnet)\b", I)
EXFIL_CHANNEL = re.compile(r"(aws\s+s3\s+(cp|sync)|az\s+storage|gsutil\s+cp|kubectl\s+get\s+secret)", I)
SECRET_SOURCE = re.compile(r"(printenv|\benv\b\s*$|\benv\b\s*\||cat\s|\$\(|<\s*\.?\w*/?\.env)", I)
PIPE_TO_SHELL = re.compile(r"\|\s*(sudo\s+)?(sh|bash|zsh|dash|python3?|node)\b", I)

# --- git gate bypass ---
GATE_BYPASS = re.compile(
    r"(--no-verify|\bgit\b[^|;&]*\bcommit\b[^|;&]*\s-[a-zA-Z]*n|core\.hooksPath|HUSKY\s*=\s*0|"
    r"(-o|--push-option)\s*ci\.skip|\benv\s+-i\b)", I)


def _current_branch():
    # symbolic-ref reports the branch even on an unborn branch (no commits yet);
    # rev-parse --abbrev-ref returns "HEAD" there. Fall back for detached HEAD.
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    for args in (["git", "symbolic-ref", "--short", "HEAD"],
                 ["git", "rev-parse", "--abbrev-ref", "HEAD"]):
        try:
            r = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and r.stdout.strip() and r.stdout.strip() != "HEAD":
                return r.stdout.strip()
        except Exception:
            pass
    return ""


def _on_protected_branch():
    b = _current_branch()
    return bool(b) and (b in ("main", "master") or b.startswith("release"))


def _audit(kind, tool, reason):
    try:
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        d = os.path.join(root, ".claude", "audit"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "security-events.jsonl"), "a") as f:
            f.write(json.dumps({"ts": datetime.now(UTC).isoformat(),
                    "hook": "delivery-guard", "decision": kind, "tool": tool, "reason": reason}) + "\n")
    except Exception:
        sys.stderr.write("delivery-guard: WARNING audit write failed (event not recorded)\n")


def decision(kind, reason, tool=""):
    if kind in ("deny", "ask"):
        _audit(kind, tool, reason)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": kind, "permissionDecisionReason": reason}}))
    sys.exit(0)


def check_bash(cmd):
    if not isinstance(cmd, str):
        decision("deny", "Bash command is not a string (possible guard-evasion via list/obj input). Blocked.", "Bash")
    c = " ".join(cmd.split())

    # gate bypass
    if re.search(r"\bgit\b", c, I) and GATE_BYPASS.search(c):
        decision("deny", "Command bypasses the commit/push gate (--no-verify / -n / core.hooksPath / HUSKY=0 / ci.skip). Run the hooks; do not skip them.", "Bash")
    if re.search(r"git\s+config\b[^|;&]*hooksPath", c, I) or re.search(r"pre-commit\s+uninstall", c, I) or re.search(r"rm\b[^|;&]*\.git/hooks", c, I):
        decision("deny", "Command disables/removes git hooks (couche 0). Blocked.", "Bash")

    # branch-per-change: don't commit/push directly on a protected branch.
    # Resolve the branch ONCE, only when a git commit/push is actually present.
    is_commit = bool(re.search(r"\bgit\s+commit\b", c, I)) and not re.search(r"--amend", c, I)
    is_push = bool(re.search(r"\bgit\s+push\b", c, I)) and not re.search(r"(--force|--force-with-lease|\s-f\b|\s\+)", c, I)
    if is_commit or is_push:
        br = _current_branch()
        if br and (br in ("main", "master") or br.startswith("release")):
            if is_commit:
                decision("ask", f"Committing directly on protected branch '{br}'. The standard is branch-per-change — create a feature branch first.", "Bash")
            else:
                decision("ask", f"Pushing directly from protected branch '{br}'. Direct pushes to main/master/release* should go via a PR.", "Bash")

    # secret files: never touch via shell
    if SECRET_FILE.search(c):
        decision("deny", "Command references a secret/credential file (.env/.ssh/key/credentials). Blocked — do not read or move secrets via shell.", "Bash")

    # secret exfiltration (literal token, or outbound/exfil-channel + secret source/env)
    if SECRET_TOKENS.search(c):
        decision("deny", "Command contains a credential/secret token. Blocked.", "Bash")
    if (OUTBOUND.search(c) or EXFIL_CHANNEL.search(c)) and (SECRET_SOURCE.search(c) or SECRET_ENV.search(c)):
        decision("deny", "Outbound/copy command pulls from a secret source (env/file/substitution) — possible exfiltration. Blocked.", "Bash")
    if re.search(r"kubectl\s+get\s+secret", c, I):
        decision("deny", "kubectl get secret dumps cluster secrets. Blocked.", "Bash")
    if re.search(r"\b(curl|wget|fetch)\b", c, I) and PIPE_TO_SHELL.search(c):
        decision("deny", "Pipe-to-shell from a network fetch (curl|wget … | sh) — arbitrary remote code. Blocked.", "Bash")

    # force-push: always ask (rare; safer to confirm than to mis-parse the target ref)
    if re.search(r"\bgit\s+push\b", c, I) and re.search(r"(--force\b|--force-with-lease\b|\s-f\b|\s\+[\w/]+(:|$))", c, I):
        decision("ask", "Force-push detected. Confirm — branch-protection should reject this on a protected branch.", "Bash")
    if re.search(r"\bgh\s+pr\s+merge\b[^|;&]*--admin", c, I):
        decision("ask", "gh pr merge --admin bypasses required checks. Confirm — defeats the merge gate.", "Bash")

    decision("allow", "", "Bash")


def check_paths(paths, tool):
    for p in paths:
        if not isinstance(p, str) or not p:
            continue
        if SECRET_FILE.search(p):
            decision("deny", f"{p} is a secret/credential file — access blocked.", tool)
        for pat in KILL_SWITCH:
            if re.search(pat, p):
                decision("deny", f"{p} is the guard's own config/hook (kill switch) — edits are blocked, not just confirmed.", tool)
        for pat in PROTECTED_PATHS:
            if re.search(pat, p):
                decision("ask", f"{p} is a couche-0 gate file. Editing it changes how delivery is enforced — confirm (normally only repo-bootstrap touches these).", tool)
    decision("allow", "", tool)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # cannot parse the wrapper at all → don't break the session
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}
    MUTATORS = ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit", "Read")
    try:
        if tool == "Bash":
            check_bash(ti.get("command", ""))
        elif tool in ("Write", "Edit", "Read", "NotebookEdit"):
            check_paths([ti.get("file_path", "") or ti.get("notebook_path", "")], tool)
        elif tool == "MultiEdit":
            check_paths([ti.get("file_path", "")] + [e.get("file_path", "") for e in ti.get("edits", []) if isinstance(e, dict)], tool)
    except SystemExit:
        raise
    except Exception:
        # fail CLOSED for mutating tools; fail open for everything else
        if tool in MUTATORS:
            decision("deny", "delivery-guard could not evaluate this call safely — blocked (fail-closed).", tool)
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
