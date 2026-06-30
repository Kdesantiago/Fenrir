#!/usr/bin/env python3
"""Smoke-test couche-0 wiring — cross-platform port of scripts/bootstrap-smoke-test.sh.

Catches the silent desyncs that leave the delivery gate full of holes:
  - org-profile.yaml missing (repo not bootstrapped)
  - pre-commit hook types not all installed (commit-msg silently no-ops otherwise)
  - CI workflow present, and its job `name:` values cover the branch-protection
    `required_checks` (the coupling that makes a check actually *required*)
  - .semgrep.yml present when a `sast`/semgrep check references it (else SAST is red forever)
  - branch-protection .tf parses / has a blocking policy — *only if* terraform config is present
  - enforcement hooks wired into .claude/settings.json

Runs on Windows / macOS / Linux with `python bootstrap_smoke_test.py`. Pure stdlib — no
PyYAML, no terraform binary, no bash. Terraform-specific asserts are skipped gracefully when
no `.tf` is present.

Run from a repo root after repo-bootstrap (or pass it as the first argument). Exits non-zero
on any gap, 0 when the gate is wired. The exit code is advisory: it *reports* findings; like
the .sh it does not itself block anything.

Usage:  python scripts/bootstrap_smoke_test.py [REPO_ROOT]
        (REPO_ROOT defaults to $CLAUDE_PROJECT_DIR, then the current directory)
"""
from __future__ import annotations

import glob
import os
import re
import sys

_fail = False


def note(msg: str) -> None:
    print(f"  - {msg}")


def bad(msg: str) -> None:
    global _fail
    print(f"FAIL: {msg}")
    _fail = True


def _repo_root(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1].strip():
        return argv[1]
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


# --- step helpers ----------------------------------------------------------------------


def check_org_profile(root: str) -> None:
    print("[1/6] org-profile.yaml present")
    if os.path.isfile(os.path.join(root, "org-profile.yaml")):
        note("ok")
    else:
        bad("org-profile.yaml missing (run repo-bootstrap)")


def check_precommit_hooks(root: str) -> None:
    print("[2/6] all three pre-commit hook types installed")
    for h in ("pre-commit", "pre-push", "commit-msg"):
        hook_path = os.path.join(root, ".git", "hooks", h)
        # pre-commit-generated hooks invoke `pre-commit hook-impl --hook-type=<h>`; match that
        # sentinel, not the bare string 'pre-commit' (a stale/hand-written hook has that too).
        if os.path.isfile(hook_path) and (f"--hook-type={h}") in _read(hook_path):
            note(f"{h} installed")
        else:
            bad(f"{h} hook not installed (run: pre-commit install --hook-type {h})")


def _ci_workflow_paths(root: str) -> list[str]:
    """GitHub workflow files that could carry the required checks. Prefer the template name
    (required-checks.yml) but accept any workflow under .github/workflows so the dogfooding
    repo (ci.yml + delivery-trace.yml) is covered too."""
    paths: list[str] = []
    preferred = os.path.join(root, ".github", "workflows", "required-checks.yml")
    if os.path.isfile(preferred):
        paths.append(preferred)
    wf_dir = os.path.join(root, ".github", "workflows")
    if os.path.isdir(wf_dir):
        for p in sorted(glob.glob(os.path.join(wf_dir, "*.yml")) + glob.glob(os.path.join(wf_dir, "*.yaml"))):
            if p not in paths:
                paths.append(p)
    return paths


def _azure_pipeline_path(root: str) -> str:
    for name in ("azure-pipeline.yml", "azure-pipelines.yml"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            return p
    return ""


def _job_names(yaml_text: str) -> set[str]:
    """Extract GitHub Actions job display names from `name: <value>` lines. Strips inline
    comments and surrounding quotes. Includes the top-level `name:` too — harmless, and some
    single-job workflows name the workflow == the status context."""
    names: set[str] = set()
    for m in re.finditer(r"^\s*name:\s*(.+?)\s*$", yaml_text, re.MULTILINE):
        val = m.group(1)
        val = val.split("#", 1)[0].strip()  # drop inline comment
        val = val.strip("'\"").strip()
        if val:
            names.add(val)
    return names


def _tf_required_checks(root: str) -> list[str]:
    """Parse the `required_checks` list default out of any *.tf in root. Pure-regex; no
    terraform binary. Returns [] when absent."""
    checks: list[str] = []
    for tf in sorted(glob.glob(os.path.join(root, "*.tf"))):
        text = _read(tf)
        # Find a `required_checks` variable/local with a default = [ ... ] list of strings.
        m = re.search(r"required_checks\b.*?default\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if not m:
            # Or a direct `contexts = [ ... ]`.
            m = re.search(r"contexts\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if m:
            for sm in re.finditer(r'"([^"]+)"', m.group(1)):
                checks.append(sm.group(1))
            if checks:
                break
    return checks


def check_ci_and_coupling(root: str) -> None:
    print("[4/6] CI present, and (GitHub) job names cover branch-protection required_checks")
    gh_paths = _ci_workflow_paths(root)
    az_ci = _azure_pipeline_path(root)

    if gh_paths:
        all_names: set[str] = set()
        for p in gh_paths:
            all_names |= _job_names(_read(p))
        shown = ", ".join(os.path.relpath(p, root) for p in gh_paths)
        note(f"GitHub workflow(s): {shown}")

        required = _tf_required_checks(root)
        if required:
            # Coupling: every required status check must be produced by a job name in CI.
            for c in required:
                if c in all_names:
                    note(f"required check '{c}' has a matching CI job name")
                else:
                    bad(
                        f"required check '{c}' (branch-protection) has NO matching job name in CI "
                        "-> the check can never go green / never blocks"
                    )
        else:
            # No terraform to couple against (e.g. template world before tf is filled). Fall
            # back to the canonical template required set.
            for c in ("test", "sast", "build"):
                if c in all_names:
                    note(f"job '{c}' present")
                else:
                    bad(f"expected job name '{c}' not found in CI workflow(s)")
    elif az_ci:
        # Azure build-validation keys on build_definition_id, not stage names — assert the
        # pipeline exists & a blocking policy references it.
        note(f"Azure pipeline {os.path.relpath(az_ci, root)} present")
        tfs = glob.glob(os.path.join(root, "*.tf"))
        joined = "".join(_read(p) for p in tfs)
        if (
            tfs
            and "azuredevops_branch_policy_build_validation" in joined
            and re.search(r"blocking\s*=\s*true", joined)
        ):
            note("blocking build-validation policy found in terraform")
        else:
            bad(
                "Azure repo: no blocking azuredevops_branch_policy_build_validation found "
                "-- the pipeline isn't a required gate"
            )
    else:
        bad("no CI workflow found (.github/workflows/*.yml or azure-pipeline*.yml)")


def check_semgrep(root: str) -> None:
    print("[5/6] .semgrep.yml present (the sast check hard-runs --config .semgrep.yml)")
    gh_paths = _ci_workflow_paths(root)
    az_ci = _azure_pipeline_path(root)
    references_semgrep = False
    for p in gh_paths:
        if "semgrep" in _read(p):
            references_semgrep = True
            break
    if not references_semgrep and az_ci and "semgrep" in _read(az_ci):
        references_semgrep = True

    if references_semgrep:
        if os.path.isfile(os.path.join(root, ".semgrep.yml")):
            note(".semgrep.yml present")
        else:
            bad(".semgrep.yml missing but a sast check references it -> SAST red forever")
    else:
        note("no semgrep check referenced; skipping")


def check_terraform(root: str) -> None:
    print("[6/6] branch-protection terraform parses (if present)")
    tfs = sorted(glob.glob(os.path.join(root, "*.tf")))
    if not tfs:
        note("skipped (no .tf present)")
        return
    # No terraform binary required: assert each .tf has balanced braces and a recognizable
    # branch-protection / build-validation resource. This is a best-effort structural parse.
    ok = True
    for tf in tfs:
        text = _read(tf)
        if text.count("{") != text.count("}"):
            bad(f"{os.path.basename(tf)}: unbalanced braces (likely invalid HCL)")
            ok = False
    joined = "".join(_read(p) for p in tfs)
    if not (
        "github_branch_protection" in joined
        or "azuredevops_branch_policy_build_validation" in joined
    ):
        note("no branch-protection resource in *.tf (informational)")
    elif ok:
        note("branch-protection terraform present and structurally parses")


def check_enforcement_hooks(root: str) -> None:
    print("[3/6] enforcement hooks wired into .claude/settings.json")
    settings = os.path.join(root, ".claude", "settings.json")
    text = _read(settings)
    if not text:
        bad(".claude/settings.json missing or empty (enforcement hooks not wired)")
        return
    # The deny-path guard is the load-bearing enforcement hook; if it's wired, the merge
    # happened. Accept either shell-string or exec-form (baked absolute interpreter).
    if "delivery-guard.py" in text:
        note("delivery-guard wired")
    else:
        bad("delivery-guard.py not referenced in .claude/settings.json -> no in-session gate")
    for h in ("prompt-guard.py", "session-context.py"):
        if h in text:
            note(f"{h} wired")
        else:
            note(f"{h} not wired (informational)")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    root = _repo_root(argv)

    check_org_profile(root)
    check_precommit_hooks(root)
    check_enforcement_hooks(root)
    check_ci_and_coupling(root)
    check_semgrep(root)
    check_terraform(root)

    print()
    if not _fail:
        print("SMOKE TEST PASSED -- couche-0 gate is wired.")
        return 0
    print("SMOKE TEST FAILED -- gate has holes above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
