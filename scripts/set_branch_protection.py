#!/usr/bin/env python3
"""Arm GitHub branch protection WITHOUT gh or terraform (R6) — pure stdlib urllib.

Couche-0's only true merge gate is the branch-protection rule. The canonical path was
`terraform apply` (needs the terraform binary + provider) or `gh api` (needs the gh CLI).
This script removes both prerequisites: if a GITHUB_TOKEN and a repo slug are available it
PUTs the rule via the GitHub REST API directly; otherwise it prints the exact GitHub web-UI
steps AND the equivalent REST payload so a human can apply it by hand.

The rule mirrors templates/branch-protection.tf (solo-maintainer tuned): PRs required, CI
strict-green required, 0 approvals (a lone maintainer can't self-approve), enforce_admins on,
linear history, no force-push, no deletions, conversation resolution required.

Inputs (all optional; the script degrades to printing instructions when they're missing):
  GITHUB_TOKEN / GH_TOKEN   a token with repo admin scope
  --repo OWNER/REPO         or env GITHUB_REPOSITORY (e.g. "octocat/Fenrir")
  --branch NAME             default: main
  --check NAME              repeatable; required status-check contexts (== CI job names)

Usage:
  python scripts/set_branch_protection.py --repo owner/Fenrir \
      --check "validate manifests" --check "lint + type + test hooks"

Pure stdlib (urllib, json, argparse). Never imports gh or terraform. Exit 0 on success or
when it printed the manual path; exit 1 only on an actual API error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# Default required status-check contexts == the job `name:` values in this repo's CI.
# Override entirely with one or more --check flags.
_DEFAULT_CHECKS = [
    "dashboard (lint + type + test)",
    "lint + type + test hooks",
    "validate manifests",
    "delivery-trace",
]


def _token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _repo_slug(arg: str | None) -> str | None:
    return arg or os.environ.get("GITHUB_REPOSITORY")


def build_payload(checks: list[str]) -> dict:
    """The branch-protection rule body, mirroring templates/branch-protection.tf."""
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": checks,
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "required_approving_review_count": 0,
            "require_code_owner_reviews": False,
            "dismiss_stale_reviews": True,
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": True,
    }


def _print_manual(repo: str | None, branch: str, payload: dict, reason: str) -> None:
    slug = repo or "<owner>/<repo>"
    print(f"Branch protection NOT applied automatically: {reason}")
    print()
    print("Option A — GitHub web UI (no CLI, no terraform):")
    print(f"  1. Open https://github.com/{slug}/settings/branches")
    print(f"  2. 'Add branch protection rule' (or edit the existing rule for '{branch}')")
    print(f"  3. Branch name pattern: {branch}")
    print("  4. Enable:")
    print("       [x] Require a pull request before merging")
    print("           - Required approvals: 0  (solo maintainer; raise to >=1 for a team)")
    print("       [x] Require status checks to pass before merging")
    print("           [x] Require branches to be up to date before merging (strict)")
    print("           Add these required checks (must equal the CI job names):")
    for c in payload["required_status_checks"]["contexts"]:
        print(f"               - {c}")
    print("       [x] Require conversation resolution before merging")
    print("       [x] Require linear history")
    print("       [x] Do not allow force pushes")
    print("       [x] Do not allow deletions")
    print("       [x] Include administrators (enforce_admins)")
    print("  5. Save changes.")
    print()
    print("Option B — equivalent REST call (set GITHUB_TOKEN with repo-admin scope, then run")
    print("           this script again, or issue it yourself):")
    print(f"  PUT https://api.github.com/repos/{slug}/branches/{branch}/protection")
    print("  Headers: Authorization: Bearer <token>")
    print("           Accept: application/vnd.github+json")
    print("           X-GitHub-Api-Version: 2022-11-28")
    print("  Body:")
    print(json.dumps(payload, indent=2))


def apply_via_api(repo: str, branch: str, token: str, payload: dict) -> int:
    url = f"https://api.github.com/repos/{repo}/branches/{branch}/protection"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "fenrir-set-branch-protection")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (https only)
            code = resp.getcode()
        print(f"Branch protection applied to {repo} @ {branch} (HTTP {code}).")
        print("Required checks:")
        for c in payload["required_status_checks"]["contexts"]:
            print(f"  - {c}")
        print()
        print("Note: also enable auto-delete of merged branches (out of protection state):")
        print(f"  PUT/PATCH repos/{repo} with delete_branch_on_merge=true")
        return 0
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        sys.stderr.write(
            f"GitHub API error {e.code} applying branch protection to {repo} @ {branch}:\n{detail}\n"
        )
        if e.code in (401, 403):
            sys.stderr.write(
                "The token lacks repo-admin scope, or branch protection requires a public repo "
                "/ GitHub Pro/Team. Falling back to manual instructions.\n"
            )
            _print_manual(repo, branch, payload, f"API returned {e.code}")
        return 1
    except urllib.error.URLError as e:
        sys.stderr.write(f"Network error reaching GitHub API: {e.reason}\n")
        _print_manual(repo, branch, payload, "network error")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arm GitHub branch protection without gh/terraform.")
    parser.add_argument("--repo", help="OWNER/REPO (else $GITHUB_REPOSITORY)")
    parser.add_argument("--branch", default="main", help="branch to protect (default: main)")
    parser.add_argument(
        "--check",
        action="append",
        dest="checks",
        help="required status-check context (== CI job name); repeatable",
    )
    args = parser.parse_args(argv if argv is not None else None)

    checks = args.checks if args.checks else list(_DEFAULT_CHECKS)
    payload = build_payload(checks)
    repo = _repo_slug(args.repo)
    token = _token()

    if not repo:
        _print_manual(repo, args.branch, payload, "no repo slug (--repo or $GITHUB_REPOSITORY)")
        return 0
    if not token:
        _print_manual(repo, args.branch, payload, "no GITHUB_TOKEN/GH_TOKEN in env")
        return 0

    return apply_via_api(repo, args.branch, token, payload)


if __name__ == "__main__":
    sys.exit(main())
