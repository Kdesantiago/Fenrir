#!/usr/bin/env bash
# Smoke-test couche-0 wiring. Catches the silent desyncs: uninstalled hook types,
# CI job-name vs branch-protection required_checks mismatch, invalid terraform.
# Run from a repo after repo-bootstrap. Exits non-zero on any gap.
set -euo pipefail

fail=0
note() { printf '  - %s\n' "$1"; }
bad()  { printf 'FAIL: %s\n' "$1"; fail=1; }

echo "[1/6] org-profile.yaml present"
[ -f org-profile.yaml ] && note "ok" || bad "org-profile.yaml missing (run repo-bootstrap)"

echo "[2/6] all three pre-commit hook types installed"
for h in pre-commit pre-push commit-msg; do
  # pre-commit-generated hooks invoke `pre-commit hook-impl --hook-type=<h>`; match that sentinel,
  # not the bare string 'pre-commit' (which a stale/hand-written hook would also contain).
  if [ -f ".git/hooks/$h" ] && grep -q -- "--hook-type=$h" ".git/hooks/$h" 2>/dev/null; then
    note "$h installed"
  else
    bad "$h hook not installed (run: pre-commit install --hook-type $h)"
  fi
done

echo "[3/6] pre-commit runs clean on all files"
if command -v pre-commit >/dev/null; then
  pre-commit run --all-files >/dev/null 2>&1 && note "ok" || bad "pre-commit run --all-files failed"
else
  bad "pre-commit not installed"
fi

echo "[4/6] CI present, and (GitHub) job names == branch-protection required_checks"
# `test` carries the coverage gate, so the required set is test/sast/build.
checks="test sast build"
gh_ci=""; az_ci=""
[ -f .github/workflows/required-checks.yml ] && gh_ci=".github/workflows/required-checks.yml"
# Match the user's real filename (singular) OR the template name (plural).
for f in azure-pipeline.yml azure-pipelines.yml; do [ -f "$f" ] && az_ci="$f"; done
if [ -n "$gh_ci" ]; then
  for c in $checks; do
    grep -qE "name: *$c\b" "$gh_ci" && note "$c job in $gh_ci" || bad "required check '$c' has no matching job name in $gh_ci"
  done
elif [ -n "$az_ci" ]; then
  # Azure build-validation keys on build_definition_id, not stage names — assert the pipeline exists & a blocking policy references it.
  note "Azure pipeline $az_ci present"
  if ls ./*.tf >/dev/null 2>&1 && grep -rq 'azuredevops_branch_policy_build_validation' ./*.tf && grep -rq 'blocking *= *true' ./*.tf; then
    note "blocking build-validation policy found in terraform"
  else
    bad "Azure repo: no blocking azuredevops_branch_policy_build_validation found — the pipeline isn't a required gate"
  fi
else
  bad "no CI workflow found (.github/workflows/required-checks.yml or azure-pipeline*.yml)"
fi

echo "[5/6] .semgrep.yml present (the sast check hard-runs --config .semgrep.yml)"
if [ -n "$gh_ci$az_ci" ] && { [ -n "$gh_ci" ] && grep -q 'semgrep' "$gh_ci"; } || { [ -n "$az_ci" ] && grep -q 'semgrep' "$az_ci"; }; then
  [ -f .semgrep.yml ] && note ".semgrep.yml present" || bad ".semgrep.yml missing but a sast check references it → SAST red forever"
else
  note "no semgrep check referenced; skipping"
fi

echo "[6/6] terraform validates (if present)"
if ls ./*.tf >/dev/null 2>&1 && command -v terraform >/dev/null; then
  terraform -chdir=. validate >/dev/null 2>&1 && note "ok" || bad "terraform validate failed"
else
  note "skipped (no .tf or terraform not installed)"
fi

echo
[ "$fail" -eq 0 ] && echo "SMOKE TEST PASSED — couche-0 gate is wired." || { echo "SMOKE TEST FAILED — gate has holes above."; exit 1; }
