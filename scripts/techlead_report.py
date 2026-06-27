#!/usr/bin/env python3
"""fenrir — Tech Lead Report generator (run by /fenrir:status).

Emits a single honest markdown report for ONE consumer repo: gate health
(arming verified via the platform API where possible), governance/exceptions,
and an onboarding summary. Stdlib only. NEVER crashes on a partial repo — every
section degrades to a clearly-labeled "not configured" and the process exits 0.

Honesty rules (enforced by the red-team on the spec):
  - No DORA metrics. Tags are SemVer release markers, not deploys; commit->tag is
    not lead time; fix:-ratio is not change-failure. We show FACTS only.
  - branch-protection is reported ARMED/NOT-ARMED only from a live API call; with
    --offline (or no gh/az) we report the IaC as "declared, NOT verified".
  - A claimed `approved_by` is unverified (no identity/PR check) and labeled so.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Pure helpers (unit-tested directly)
# ---------------------------------------------------------------------------


def parse_semver(v: str) -> tuple[int, int]:
    """(major, minor) from 'X.Y.Z' (quotes/whitespace tolerated). Raises on junk."""
    parts = (v or "").strip().strip("\"'").split(".")
    return int(parts[0]), (int(parts[1]) if len(parts) > 1 else 0)


def template_version_compat(profile_ver: str, plugin_ver: str) -> tuple[bool, str]:
    """Canonical delivery-gates rule: major must match; if major==0, minor too; patch ignored."""
    try:
        p_maj, p_min = parse_semver(profile_ver)
        i_maj, i_min = parse_semver(plugin_ver)
    except Exception:
        return False, f"unparseable version (profile={profile_ver!r}, plugin={plugin_ver!r})"
    if p_maj != i_maj:
        return False, f"major differs: profile {profile_ver} vs plugin {plugin_ver}"
    if p_maj == 0 and p_min != i_min:
        return False, f"0.x minor differs: profile {profile_ver} vs plugin {plugin_ver}"
    return True, f"{profile_ver} ~ {plugin_ver}"


def parse_org_profile(text: str) -> dict[str, str]:
    """Top-level `key: value` pairs from org-profile.yaml (no yaml dep; comments stripped)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        raw = raw.split("#", 1)[0].strip().strip("\"'")
        if raw:
            out[key] = raw
    return out


def classify_exception(entry: dict, today: date) -> dict:
    """Annotate one gate-exception with open/lapsed/self-granted/approved status."""
    status = entry.get("status", "open")
    expires = entry.get("expires", "")
    granted_by = entry.get("granted_by", "")
    approved_by = entry.get("approved_by", "")
    lapsed = False
    if expires:
        try:
            lapsed = date.fromisoformat(expires) < today
        except ValueError:
            lapsed = False
    approved = bool(approved_by) and approved_by != granted_by
    return {
        "id": entry.get("id", "?"),
        "rule": entry.get("rule", "?"),
        "granted_by": granted_by or "?",
        "approved_by": approved_by,
        "expires": expires or "?",
        "open": status == "open",
        "lapsed": lapsed,
        "self_granted": not approved,
    }


def read_exceptions(root: Path) -> list[dict]:
    """Parse gate-exceptions.jsonl, skipping unparseable lines. [] if absent."""
    f = root / "docs" / "delivery-memory" / "gate-exceptions.jsonl"
    if not f.exists():
        return []
    out: list[dict] = []
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


# ---------------------------------------------------------------------------
# Repo inspection
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def precommit_state(root: Path) -> str:
    cfg = (root / ".pre-commit-config.yaml").exists()
    installed = (root / ".git" / "hooks" / "pre-commit").exists() or bool(
        _git(root, "config", "core.hooksPath")
    )
    if cfg and installed:
        return "✅ configured + installed"
    if cfg:
        return "⚠️ config present, git hooks NOT installed (`pre-commit install`)"
    return "❌ no .pre-commit-config.yaml"


def ci_state(root: Path) -> str:
    gh = list((root / ".github" / "workflows").glob("*.y*ml")) if (
        root / ".github" / "workflows"
    ).is_dir() else []
    azure = list(root.glob("azure-pipelines*.y*ml"))
    if gh:
        return f"✅ GitHub workflow present ({len(gh)} file(s)) — pipeline file present, required-status wiring not asserted"
    if azure:
        return "✅ Azure pipeline present — pipeline file present, required-status wiring not asserted"
    return "❌ no CI workflow found (.github/workflows or azure-pipelines*.yml)"


def _origin_owner_repo(root: Path) -> tuple[str, str] | None:
    url = _git(root, "remote", "get-url", "origin")
    if not url:
        return None
    m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$", url)
    if not m:
        return None
    return m.group(1), m.group(2)


def _default_branch(root: Path) -> str:
    b = _git(root, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if b and "/" in b:
        return b.split("/", 1)[1]
    return _git(root, "branch", "--show-current") or "main"


def branch_protection_state(root: Path, offline: bool, branch: str | None = None) -> str:
    """ARMED/NOT-ARMED via live gh api when possible; else declared-not-verified."""
    tf_declared = (root / "branch-protection.tf").exists() or (
        root / "azure-branch-policy.tf"
    ).exists()
    declared = "IaC declared" if tf_declared else "no branch-protection IaC found"

    if offline or not shutil.which("gh"):
        why = "offline" if offline else "`gh` not available"
        return f"🔒❓ {declared} — NOT verified applied ({why}; run online with `gh` to confirm arming)"

    owner_repo = _origin_owner_repo(root)
    if not owner_repo:
        return f"🔒❓ {declared} — could not resolve a GitHub origin to verify arming"
    owner, repo = owner_repo
    br = branch or _default_branch(root)
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/branches/{br}/protection"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as e:
        return f"🔒❓ {declared} — verification call failed ({e}); treat as unknown"
    if r.returncode == 0:
        return f"✅ ARMED (verified): branch protection active on `{br}`"
    if "Branch not protected" in (r.stderr + r.stdout) or '"status":"404"' in r.stdout:
        return f"❌ NOT-ARMED (verified): no protection on `{br}` — {declared} but not applied"
    return f"🔒❓ {declared} — could not read protection for `{br}` (auth/permissions?); treat as unknown"


def template_drift(root: Path, plugin_root: Path | None) -> str:
    prof = root / "org-profile.yaml"
    if not prof.exists():
        return "— no org-profile.yaml (not a bootstrapped repo)"
    profile_ver = parse_org_profile(prof.read_text()).get("template_version", "")
    if not profile_ver:
        return "⚠️ org-profile.yaml has no template_version"
    plugin_ver = ""
    if plugin_root:
        pj = plugin_root / ".claude-plugin" / "plugin.json"
        if pj.exists():
            try:
                plugin_ver = json.loads(pj.read_text()).get("version", "")
            except ValueError:
                plugin_ver = ""
    if not plugin_ver:
        return f"⚠️ template_version {profile_ver} (installed plugin version unknown — set CLAUDE_PLUGIN_ROOT)"
    ok, reason = template_version_compat(profile_ver, plugin_ver)
    return ("✅ " if ok else "❌ DRIFT — ") + reason


def last_release(root: Path) -> str:
    tag = _git(root, "describe", "--tags", "--abbrev=0", "--match", "v*")
    if not tag:
        return "no `v*` release tag yet"
    when = _git(root, "log", "-1", "--format=%as", tag)
    return f"{tag}" + (f" ({when})" if when else "")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render(root: Path, plugin_root: Path | None, offline: bool, branch: str | None,
           today: date) -> str:
    prof = root / "org-profile.yaml"
    profile = parse_org_profile(prof.read_text()) if prof.exists() else {}
    exc = [classify_exception(e, today) for e in read_exceptions(root)]
    open_exc = [e for e in exc if e["open"]]

    lines: list[str] = []
    lines.append(f"# 🐺 Tech Lead Report — `{root.name}`")
    lines.append("")
    lines.append("> Honest by construction: every line is a verified fact or labeled "
                 "declared/unverified. No DORA proxies (see the spec for why).")
    lines.append("")

    lines.append("## 1. Gate health")
    lines.append(f"- **pre-commit:** {precommit_state(root)}")
    lines.append(f"- **CI required-checks:** {ci_state(root)}")
    lines.append(f"- **branch-protection:** {branch_protection_state(root, offline, branch)}")
    lines.append(f"- **template_version:** {template_drift(root, plugin_root)}")
    lines.append("")

    lines.append("## 2. Governance — gate exceptions")
    if not open_exc:
        lines.append("- No open gate-exceptions. ✅")
    else:
        for e in open_exc:
            flags = []
            if e["lapsed"]:
                flags.append("⏰ LAPSED (past expiry, still open → run `expire`)")
            if e["self_granted"]:
                flags.append("🚩 self-granted (claimed approver unverified)")
            else:
                flags.append(f"✅ approved by {e['approved_by']} (unverified)")
            lines.append(
                f"- `{e['rule']}` (id {e['id']}, by {e['granted_by']}, until {e['expires']}) — "
                + "; ".join(flags)
            )
    lines.append("")

    lines.append("## 3. Onboarding — how we deliver here")
    if profile:
        stack = ", ".join(
            f"{k}={profile[k]}"
            for k in ("platform", "framework", "auth_provider", "obs_backend",
                      "llm_provider", "front")
            if k in profile
        )
        lines.append(f"- **Declared stack:** {stack or '(none declared)'}")
    else:
        lines.append("- **Declared stack:** no org-profile.yaml — run `repo-bootstrap`.")
    lines.append("- **The gate (couche 0):** pre-commit + in-session hooks + CI "
                 "required-checks + branch-protection. It only blocks once "
                 "`terraform apply` has armed branch-protection.")
    lines.append("- **Golden path:** `/fenrir:challenge-me <idea>` → `/fenrir:deliver "
                 "<task>` → `/fenrir:ship`.")
    lines.append(f"- **Last release:** {last_release(root)}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fenrir Tech Lead Report")
    ap.add_argument("--root", help="repo to inspect (default: $CLAUDE_PROJECT_DIR or cwd)")
    ap.add_argument("--offline", action="store_true",
                    help="skip the live branch-protection API call")
    ap.add_argument("--branch", help="branch to check protection on (default: repo default)")
    args = ap.parse_args(argv)

    root = Path(args.root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    pr = os.environ.get("CLAUDE_PLUGIN_ROOT")
    plugin_root = Path(pr) if pr else None
    try:
        print(render(root, plugin_root, args.offline, args.branch, date.today()))
    except Exception as e:  # never crash a report; surface the failure honestly
        print(f"# Tech Lead Report\n\n⚠️ report generation hit an error: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
