"""Tests for scripts/techlead_report.py (the /fenrir:status helper).

Self-contained (no conftest). Imports the helper from scripts/, exercises the pure
functions + a graceful end-to-end render against tmp-repo fixtures in --offline mode
(no network / no gh). The semver-compat cases are pinned to the canonical
delivery-gates rule (major match; 0.x => minor match; patch ignored).
"""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import techlead_report as tr  # noqa: E402


# --- template_version_compat: pinned to the delivery-gates rule ---
@pytest.mark.parametrize(
    "profile,plugin,expected",
    [
        ("1.2.0", "1.5.9", True),   # same major -> minor/patch ignored
        ("2.9.9", "2.0.0", True),   # same major, older plugin minor -> still compatible
        ("1.0.0", "2.0.0", False),  # major differs
        ("0.1.0", "0.1.9", True),   # 0.x, same minor -> ok
        ("0.1.0", "0.2.0", False),  # 0.x, minor differs -> incompatible
        ("0.3.4", "0.3.0", True),   # 0.x same minor, patch ignored
    ],
)
def test_template_version_compat(profile, plugin, expected):
    ok, _ = tr.template_version_compat(profile, plugin)
    assert ok is expected


def test_template_version_compat_unparseable():
    ok, reason = tr.template_version_compat("", "x.y")
    assert ok is False
    assert "unparseable" in reason


def test_parse_semver():
    assert tr.parse_semver('"1.2.3"') == (1, 2)
    assert tr.parse_semver("3") == (3, 0)


# --- parse_org_profile ---
def test_parse_org_profile_strips_comments_and_quotes():
    text = 'platform: aks            # comment\nframework: "fastapi"\ntemplate_version: 1.1.1\nblank:\n'
    p = tr.parse_org_profile(text)
    assert p["platform"] == "aks"
    assert p["framework"] == "fastapi"
    assert p["template_version"] == "1.1.1"
    assert "blank" not in p  # empty value dropped


# --- classify_exception ---
TODAY = date(2026, 6, 27)


def test_classify_self_granted_when_no_approver():
    e = tr.classify_exception(
        {"id": "ge-1", "rule": "cov", "granted_by": "a@x", "expires": "2026-07-27", "status": "open"},
        TODAY,
    )
    assert e["self_granted"] is True
    assert e["lapsed"] is False
    assert e["open"] is True


def test_classify_self_granted_when_approver_equals_granter():
    e = tr.classify_exception(
        {"id": "ge-2", "rule": "cov", "granted_by": "a@x", "approved_by": "a@x",
         "expires": "2026-07-27", "status": "open"},
        TODAY,
    )
    assert e["self_granted"] is True


def test_classify_approved_when_distinct_approver():
    e = tr.classify_exception(
        {"id": "ge-3", "rule": "cov", "granted_by": "a@x", "approved_by": "lead@x",
         "expires": "2026-07-27", "status": "open"},
        TODAY,
    )
    assert e["self_granted"] is False
    assert e["approved_by"] == "lead@x"


def test_classify_lapsed_when_expired():
    e = tr.classify_exception(
        {"id": "ge-4", "rule": "cov", "granted_by": "a@x", "expires": "2026-01-01", "status": "open"},
        TODAY,
    )
    assert e["lapsed"] is True


def test_classify_bad_expiry_is_not_lapsed():
    e = tr.classify_exception(
        {"id": "ge-5", "rule": "cov", "granted_by": "a@x", "expires": "nope", "status": "open"},
        TODAY,
    )
    assert e["lapsed"] is False


# --- read_exceptions ---
def _write_exc(root: Path, *lines: str) -> None:
    d = root / "docs" / "delivery-memory"
    d.mkdir(parents=True)
    (d / "gate-exceptions.jsonl").write_text("\n".join(lines) + "\n")


def test_read_exceptions_missing_file(tmp_path):
    assert tr.read_exceptions(tmp_path) == []


def test_read_exceptions_skips_bad_and_nondict_lines(tmp_path):
    _write_exc(
        tmp_path,
        json.dumps({"id": "ge-1", "rule": "cov", "status": "open"}),
        "{not json",
        "[1,2,3]",
        "",
        json.dumps({"id": "ge-2", "rule": "lint", "status": "closed"}),
    )
    out = tr.read_exceptions(tmp_path)
    assert [e["id"] for e in out] == ["ge-1", "ge-2"]


# --- gate-health file checks ---
def test_precommit_states(tmp_path):
    assert "no .pre-commit" in tr.precommit_state(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n")
    assert "NOT installed" in tr.precommit_state(tmp_path)
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\n")
    assert "configured + installed" in tr.precommit_state(tmp_path)


def test_ci_state_github_azure_none(tmp_path):
    assert "no CI" in tr.ci_state(tmp_path)
    azure = tmp_path / "azure-pipelines.yml"
    azure.write_text("stages: []\n")
    assert "Azure" in tr.ci_state(tmp_path)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("on: push\n")
    assert "GitHub" in tr.ci_state(tmp_path)


def test_branch_protection_offline_declared_vs_absent(tmp_path):
    # offline => never reports ARMED; reflects IaC presence only, labeled not-verified
    s = tr.branch_protection_state(tmp_path, offline=True)
    assert "NOT verified" in s and "no branch-protection IaC" in s
    (tmp_path / "branch-protection.tf").write_text("# tf\n")
    s2 = tr.branch_protection_state(tmp_path, offline=True)
    assert "IaC declared" in s2 and "NOT verified" in s2
    assert "ARMED (verified)" not in s2


def test_template_drift_no_profile(tmp_path):
    assert "no org-profile" in tr.template_drift(tmp_path, None)


def test_template_drift_reports_drift(tmp_path):
    (tmp_path / "org-profile.yaml").write_text('template_version: "1.0.0"\n')
    plugin = tmp_path / "plug"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": "2.0.0"}))
    out = tr.template_drift(tmp_path, plugin)
    assert "DRIFT" in out


# --- end-to-end render (offline) ---
def test_render_empty_repo_is_graceful(tmp_path):
    md = tr.render(tmp_path, None, offline=True, branch=None, today=TODAY)
    assert "# 🐺 Tech Lead Report" in md
    assert "## 1. Gate health" in md
    assert "## 2. Governance" in md
    assert "## 3. Onboarding" in md
    assert "no org-profile" in md
    assert "No open gate-exceptions" in md


def test_render_flags_self_granted_and_lapsed(tmp_path):
    (tmp_path / "org-profile.yaml").write_text("platform: aks\nframework: fastapi\n")
    _write_exc(
        tmp_path,
        json.dumps({"id": "ge-1", "rule": "coverage", "granted_by": "a@x",
                    "expires": "2026-01-01", "status": "open"}),  # self-granted + lapsed
        json.dumps({"id": "ge-2", "rule": "lint", "granted_by": "a@x", "approved_by": "lead@x",
                    "expires": "2026-12-01", "status": "open"}),  # approved
    )
    md = tr.render(tmp_path, None, offline=True, branch=None, today=TODAY)
    assert "self-granted" in md
    assert "LAPSED" in md
    assert "approved by lead@x" in md
    assert "platform=aks" in md


def test_main_exits_zero_on_empty_dir(tmp_path, capsys):
    rc = tr.main(["--root", str(tmp_path), "--offline"])
    assert rc == 0
    assert "Tech Lead Report" in capsys.readouterr().out
