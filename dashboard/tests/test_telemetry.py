"""Tests for backend.telemetry — parsing crafted ~/.claude transcripts.

Self-contained (no conftest / __init__). Writes crafted *.jsonl under a tmp fake
~/.claude tree; never touches the real repo data or the real ~/.claude.
"""
from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

import pytest

from backend import telemetry

# --- fixtures-as-helpers --------------------------------------------------------------

PROJECT = "-Users-someone-proj"
OTHER_PROJECT = "-Users-someone-other"


def _line(obj: dict) -> str:
    return json.dumps(obj)


def _msg(
    *,
    model: str = "claude-opus-4",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation: int = 0,
    cache_read: int = 0,
    ts: str = "2026-06-01T10:00:00Z",
    session_id: str = "sess-1",
    sidechain: bool = False,
    skill: str | None = None,
) -> dict:
    obj: dict = {
        "timestamp": ts,
        "sessionId": session_id,
        "isSidechain": sidechain,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    if skill is not None:
        obj["attributionSkill"] = skill
    return obj


def _build_tree(tmp_path):
    """Create a fake ~/.claude with crafted transcripts. Returns claude_dir.

    Project transcript holds:
      e1 main opus       (in/out/cache, day 06-01)
      e2 sidechain sonnet, skill=fenrir:deliver  (day 06-01)
      e3 main haiku,  skill=fenrir:ship          (day 06-02)
      + a non-usage assistant line   -> skipped (no usage)
      + a malformed JSON line        -> skipped
    A nested subdir transcript holds:
      e4 main opus, no skill         (day 06-02)
    A second project (other) holds one event that filtering must exclude.
    """
    claude_dir = tmp_path / "fake_claude"
    proj = claude_dir / "projects" / PROJECT
    proj.mkdir(parents=True)

    main_lines = [
        _line(_msg(model="claude-opus-4", input_tokens=1000, output_tokens=200,
                   cache_creation=500, cache_read=100,
                   ts="2026-06-01T10:00:00Z", session_id="sess-1")),
        _line(_msg(model="claude-sonnet-4", input_tokens=2000, output_tokens=400,
                   ts="2026-06-01T11:00:00Z", session_id="sess-1",
                   sidechain=True, skill="fenrir:deliver")),
        _line(_msg(model="claude-haiku-4", input_tokens=300, output_tokens=50,
                   ts="2026-06-02T09:00:00Z", session_id="sess-2",
                   skill="fenrir:ship")),
        # non-usage line (a user message — no message.usage) -> must be skipped
        _line({"timestamp": "2026-06-02T09:01:00Z", "sessionId": "sess-2",
               "message": {"role": "user", "content": "hi"}}),
        # malformed JSON line -> must be skipped
        "{not valid json,,,",
        "",  # blank line -> skipped
    ]
    (proj / "main.jsonl").write_text("\n".join(main_lines) + "\n")

    # nested transcript (e.g. a workflow subagent under a session subdir)
    nested = proj / "sub-session"
    nested.mkdir()
    (nested / "agent.jsonl").write_text(
        _line(_msg(model="claude-opus-4", input_tokens=800, output_tokens=120,
                   ts="2026-06-02T12:00:00Z", session_id="sess-3")) + "\n"
    )

    # a different project that project-filtering must exclude
    other = claude_dir / "projects" / OTHER_PROJECT
    other.mkdir(parents=True)
    (other / "x.jsonl").write_text(
        _line(_msg(model="claude-opus-4", input_tokens=9999, output_tokens=9999,
                   ts="2026-06-05T00:00:00Z", session_id="sess-x")) + "\n"
    )

    return claude_dir


# --- encode_project (cross-platform) --------------------------------------------------


def test_encode_project_posix_byte_identical():
    # POSIX path: no drive/backslash/colon -> historical `/` `.` -> `-` only. The leading char is
    # the drive-induced separator on Windows, so assert the stable suffix (Linux CI sees `-a-b-c`).
    assert telemetry.encode_project(Path("/a/b.c")).endswith("-a-b-c")


def test_encode_project_windows_path_lowercases_drive_and_replaces_seps(monkeypatch):
    # `C:\Users\me\repo` -> `c--Users-me-repo`: drive lowercased, `:` and `\` -> `-`.
    # encode_project() calls path.resolve(), so a *literal* Windows path on a POSIX host never
    # yields a drive letter (resolve() prepends the POSIX cwd) and the drive-lowercasing branch
    # would not run. Mock .resolve() to return a real drive-bearing PureWindowsPath so that branch
    # is exercised cross-platform — the product code is correct; we drive it to the Windows case.
    win = PureWindowsPath(r"C:\Users\me\repo")
    assert win.drive == "C:"  # carries a drive letter regardless of host OS
    monkeypatch.setattr(Path, "resolve", lambda self, *a, **k: win)
    enc = telemetry.encode_project(Path(r"C:\Users\me\repo"))
    assert enc == "c--Users-me-repo"
    assert enc.startswith("c-")  # drive letter lowercased, colon -> "-"
    assert enc.endswith("Users-me-repo")
    assert ":" not in enc and "\\" not in enc and "/" not in enc


# --- encode_project: edge paths (UNC / no-drive / trailing separator) ------------------
# Universal post-condition of encode_project, OS-independent: it never raises and NO raw
# separator (`\` `/` `:` `.`) survives in the slug. The drive-lowercasing is asserted only
# when the resolved path actually has a drive letter (Windows), so these pass on Linux CI too.


def _assert_clean_slug(enc: str) -> None:
    assert isinstance(enc, str) and enc  # no crash, non-empty
    for sep in ("\\", "/", ":", "."):
        assert sep not in enc, f"separator {sep!r} survived in {enc!r}"


def test_encode_project_unc_path_no_crash_and_dash_joined():
    # UNC `\\server\share\repo`: on Windows .resolve() keeps the UNC root (drive == r"\\server\share",
    # no drive *letter* to lowercase); on POSIX it is just a backslash-laden relative name. Either way
    # the slug must be dash-joined with no surviving separators and the function must not raise.
    enc = telemetry.encode_project(Path(r"\\server\share\repo"))
    _assert_clean_slug(enc)
    assert "server" in enc and "share" in enc and enc.endswith("repo")


def test_encode_project_no_drive_path_no_crash():
    # A path with no drive letter. On POSIX it stays drive-less (drive == ""), exercising the
    # `if drive and ...` false branch; on Windows .resolve() prepends the cwd drive. Either way:
    # no crash, dash-joined, no surviving separators.
    enc = telemetry.encode_project(Path("relative/sub/dir"))
    _assert_clean_slug(enc)
    assert enc.endswith("dir")


def test_encode_project_trailing_separator_is_normalized():
    # A trailing separator must not produce a dangling `-` or a different slug than the
    # separator-free form: .resolve() strips it, so both encode identically.
    with_sep = telemetry.encode_project(Path("C:/Users/me/repo/"))
    without_sep = telemetry.encode_project(Path("C:/Users/me/repo"))
    _assert_clean_slug(with_sep)
    assert with_sep == without_sep
    assert not with_sep.endswith("-")  # no dangling trailing dash from the stripped separator


def test_encode_project_lowercases_drive_letter_when_present():
    # When the resolved path carries a single-letter drive (always true on Windows), that letter
    # is lowercased per Claude's convention. Skips on POSIX where there is no drive letter.
    resolved = Path("C:/Users/me/repo").resolve()
    drive = resolved.drive  # "C:" on Windows, "" on POSIX
    if not (len(drive) == 2 and drive[0].isalpha() and drive[1] == ":"):
        pytest.skip("no single-letter drive on this platform")
    enc = telemetry.encode_project(Path("C:/Users/me/repo"))
    assert enc[0] == drive[0].lower()  # leading drive letter lowercased
    assert enc[0].islower()


# --- consumption floor (FENRIR_DASH_SINCE) --------------------------------------------


def test_load_events_floors_by_since(tmp_path, monkeypatch):
    claude_dir = _build_tree(tmp_path)
    # day 06-01 events (e1, e2) are before the floor; 06-02 onward (e3, e4) survive.
    monkeypatch.setenv("FENRIR_DASH_SINCE", "2026-06-02")
    events = telemetry.load_events(claude_dir, PROJECT)
    assert {e["day"] for e in events} == {"2026-06-02"}
    assert len(events) == 2  # e3 + e4


def test_load_events_no_floor_when_unset(tmp_path, monkeypatch):
    claude_dir = _build_tree(tmp_path)
    monkeypatch.delenv("FENRIR_DASH_SINCE", raising=False)
    assert len(telemetry.load_events(claude_dir, PROJECT)) == 4


# --- consumption floor: lexicographic boundary (==, just-before, empty ts) -------------
# The floor is a lexicographic `ev["ts"] < since` drop. The boundary cases the coder deferred:
#   ts == since (date-only)            -> KEPT  (>= floor)
#   ts strictly before (date or full)  -> DROPPED
#   an ISO ts on the floor date        -> KEPT  ("2026-06-02T..." is NOT < "2026-06-02")
#   empty/missing ts                   -> KEPT  (no ts to compare; `since and ev["ts"]` short-circuits)


def _floor_tree(tmp_path, lines: list[str]):
    claude_dir = tmp_path / "fake_claude"
    proj = claude_dir / "projects" / PROJECT
    proj.mkdir(parents=True)
    (proj / "main.jsonl").write_text("\n".join(lines) + "\n")
    return claude_dir


def test_floor_keeps_ts_equal_to_since_drops_strictly_before(tmp_path, monkeypatch):
    monkeypatch.setenv("FENRIR_DASH_SINCE", "2026-06-02")
    cd = _floor_tree(tmp_path, [
        _line(_msg(ts="2026-06-02", session_id="eq", input_tokens=1)),            # == floor -> KEPT
        _line(_msg(ts="2026-06-02T09:00:00Z", session_id="same-day", input_tokens=1)),  # same day, later -> KEPT
        _line(_msg(ts="2026-06-01", session_id="before-date", input_tokens=1)),   # date < floor -> DROPPED
        _line(_msg(ts="2026-06-01T23:59:59Z", session_id="before-full", input_tokens=1)),  # full < floor -> DROPPED
    ])
    events = telemetry.load_events(cd, PROJECT)
    kept = {e["session_id"] for e in events}
    assert kept == {"eq", "same-day"}
    # the exact-equal event is retained (>= floor), the strictly-earlier ones excluded
    assert "eq" in kept
    assert "before-date" not in kept and "before-full" not in kept


def test_floor_keeps_event_with_empty_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("FENRIR_DASH_SINCE", "2026-06-02")
    cd = _floor_tree(tmp_path, [
        _line(_msg(ts="", session_id="no-ts", input_tokens=1)),          # empty ts -> KEPT (uncomparable)
        _line(_msg(ts="2026-06-01", session_id="before", input_tokens=1)),  # before floor -> DROPPED
    ])
    events = telemetry.load_events(cd, PROJECT)
    kept = {e["session_id"] for e in events}
    assert "no-ts" in kept           # empty ts is never floored out
    assert "before" not in kept
    # the empty-ts event still parsed as a real event (just with no day)
    no_ts = next(e for e in events if e["session_id"] == "no-ts")
    assert no_ts["ts"] == "" and no_ts["day"] == ""


# --- consumption floor: tz-correctness (epoch compare, not raw lexicographic) ----------


def test_before_floor_is_tz_correct_not_lexicographic():
    # 2026-06-01T23:00:00-05:00 == 2026-06-02T04:00:00Z. A raw `ts < since` would WRONGLY drop it
    # ("...06-01..." < "2026-06-02"); the epoch compare keeps it (it is AFTER the UTC floor).
    assert telemetry._before_floor("2026-06-01T23:00:00-05:00", "2026-06-02") is False
    # a genuinely earlier instant is dropped
    assert telemetry._before_floor("2026-06-01T10:00:00Z", "2026-06-02") is True
    # equal instant is a tie -> kept (not strictly before)
    assert telemetry._before_floor("2026-06-02T00:00:00Z", "2026-06-02") is False
    # a Z timestamp earlier than a full-ISO floor with offset, compared correctly across offsets
    assert telemetry._before_floor("2026-06-02T04:59:00Z", "2026-06-02T00:00:00-05:00") is True


def test_before_floor_string_fallback_on_unparseable():
    # unparseable side -> best-effort string compare; empty ts is never floored.
    assert telemetry._before_floor("", "2026-06-02") is False
    assert telemetry._before_floor("2026-06-01T10:00:00Z", "") is False


# --- find_transcripts -----------------------------------------------------------------


def test_find_transcripts_picks_up_nested_files(tmp_path):
    claude_dir = _build_tree(tmp_path)
    paths = telemetry.find_transcripts(claude_dir, PROJECT)
    names = sorted(p.name for p in paths)
    assert names == ["agent.jsonl", "main.jsonl"]
    # nested file is under a subdir, proving rglob recursion
    assert any(p.parent.name == "sub-session" for p in paths)


def test_find_transcripts_missing_base_returns_empty(tmp_path):
    # no projects/ dir at all
    assert telemetry.find_transcripts(tmp_path / "nope") == []


def test_find_transcripts_missing_project_returns_empty(tmp_path):
    claude_dir = _build_tree(tmp_path)
    assert telemetry.find_transcripts(claude_dir, "-no-such-project") == []


# --- load_events ----------------------------------------------------------------------


def test_load_events_count_with_project_filter(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    # e1,e2,e3 (main.jsonl) + e4 (nested) = 4; non-usage + malformed skipped;
    # other project excluded by filtering
    assert len(events) == 4
    assert all(e["model"].startswith("claude-") for e in events)


def test_load_events_all_projects_includes_other(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir)  # project=None -> every project
    assert len(events) == 5


# --- summary --------------------------------------------------------------------------


def test_summary_totals(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    s = telemetry.summary(events)

    assert s["calls"] == 4
    # input: 1000 + 2000 + 300 + 800
    assert s["input_tokens"] == 4100
    # output: 200 + 400 + 50 + 120
    assert s["output_tokens"] == 770
    # cache (creation + read): only e1 -> 500 + 100
    assert s["cache_tokens"] == 600
    # total = input + output + cache
    assert s["total_tokens"] == 4100 + 770 + 600
    assert s["cost_usd"] > 0
    assert s["models"] == ["claude-haiku-4", "claude-opus-4", "claude-sonnet-4"]
    assert s["sessions"] == 3  # sess-1, sess-2, sess-3
    assert s["first_day"] == "2026-06-01"
    assert s["last_day"] == "2026-06-02"


def test_summary_cost_matches_pricing(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    s = telemetry.summary(events)
    expected = round(sum(e["cost"] for e in events), 4)
    assert s["cost_usd"] == expected
    # sanity: opus e1 cost component is non-trivial
    assert expected > 0


# --- by_model -------------------------------------------------------------------------


def test_by_model_grouping(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    rows = telemetry.by_model(events)
    by_key = {r["key"]: r for r in rows}

    assert set(by_key) == {"claude-opus-4", "claude-sonnet-4", "claude-haiku-4"}
    # opus has two events (e1 + e4)
    assert by_key["claude-opus-4"]["calls"] == 2
    assert by_key["claude-opus-4"]["input_tokens"] == 1000 + 800
    assert by_key["claude-opus-4"]["output_tokens"] == 200 + 120
    assert by_key["claude-sonnet-4"]["calls"] == 1
    assert by_key["claude-haiku-4"]["calls"] == 1
    # sorted by cost descending
    costs = [r["cost_usd"] for r in rows]
    assert costs == sorted(costs, reverse=True)


def test_group_rows_expose_cache_columns(tmp_path):
    events = telemetry.load_events(_build_tree(tmp_path), PROJECT)
    rows = telemetry.by_model(events)
    for r in rows:
        assert "cache_write_tokens" in r and "cache_read_tokens" in r
    opus = next(r for r in rows if r["key"] == "claude-opus-4")
    assert opus["cache_read_tokens"] >= 100  # e1 had cache_read=100
    assert opus["cache_write_tokens"] >= 500  # e1 had cache_creation=500


def test_summary_cost_breakdown_reconciles_to_total(tmp_path):
    events = telemetry.load_events(_build_tree(tmp_path), PROJECT)
    s = telemetry.summary(events)
    assert s["cache_read_tokens"] >= 100 and s["cache_write_tokens"] >= 500
    b = s["cost_breakdown"]
    assert set(b) == {"input", "output", "cache_read", "cache_write"}
    # the four components reconcile to the reported total (cache_write is the remainder)
    assert sum(b.values()) == pytest.approx(s["cost_usd"], abs=0.001)


def test_efficiency_shape_and_reconciles(tmp_path):
    eff = telemetry.efficiency(telemetry.load_events(_build_tree(tmp_path), PROJECT))
    assert eff["by_model"] and eff["total"]
    t = eff["total"]
    assert t["savings"] == pytest.approx(t["uncached_cost"] - t["actual_cost"], abs=0.001)
    assert 0.0 <= t["cache_hit_ratio"] <= 1.0
    for r in eff["by_model"]:
        assert 0.0 <= r["cache_hit_ratio"] <= 1.0
        assert r["savings"] == pytest.approx(r["uncached_cost"] - r["actual_cost"], abs=0.001)


def test_efficiency_positive_savings_when_reads_dominate(tmp_path):
    # reads >> writes → caching clearly wins (savings > 0, high hit-ratio).
    cd = tmp_path / "c"
    proj = cd / "projects" / PROJECT / "s"
    proj.mkdir(parents=True)
    ev = json.dumps({"timestamp": "2026-06-01T10:00:00Z", "sessionId": "s",
        "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": 1000, "output_tokens": 100,
            "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 1_000_000}}})
    (proj / "m.jsonl").write_text(ev + "\n")
    t = telemetry.efficiency(telemetry.load_events(cd, PROJECT))["total"]
    assert t["savings"] > 0 and t["cache_hit_ratio"] > 0.9


def test_efficiency_negative_savings_when_writes_dominate(tmp_path):
    # writes (1.25x premium) with no reads → caching COSTS more than uncached (the waste signal).
    cd = tmp_path / "c"
    proj = cd / "projects" / PROJECT / "s"
    proj.mkdir(parents=True)
    ev = json.dumps({"timestamp": "2026-06-01T10:00:00Z", "sessionId": "s",
        "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": 0, "output_tokens": 0,
            "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 0}}})
    (proj / "m.jsonl").write_text(ev + "\n")
    t = telemetry.efficiency(telemetry.load_events(cd, PROJECT))["total"]
    assert t["savings"] < 0 and t["cache_hit_ratio"] == 0.0


# --- efficiency: calls + cache_read_per_call ------------------------------------------
# `efficiency(events)` consumes the flat load_events shape directly; build those dicts
# in-line (no transcript needed) so cache_read values are exact and averages deterministic.


def _ev(*, model: str, cache_read: int, input_tokens: int = 0, output_tokens: int = 0,
        cache_creation: int = 0, cost: float = 0.0) -> dict:
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation": cache_creation,
        "cache_read": cache_read,
        "cost": cost,
    }


def test_efficiency_per_model_calls_and_cache_read_per_call():
    # one model, two calls with known reads (100, 300) -> calls=2, per_call=round(400/2)=200.
    events = [
        _ev(model="claude-opus-4-8", cache_read=100, cost=0.10),
        _ev(model="claude-opus-4-8", cache_read=300, cost=0.30),
    ]
    rows = telemetry.efficiency(events)["by_model"]
    by_model = {r["model"]: r for r in rows}
    opus = by_model["claude-opus-4-8"]
    assert opus["calls"] == 2
    assert opus["cache_read_tokens"] == 400
    assert opus["cache_read_per_call"] == round(400 / 2) == 200


def test_efficiency_calls_counted_per_model():
    # three opus calls + one sonnet call -> calls split by model, not merged.
    events = [
        _ev(model="claude-opus-4-8", cache_read=100, cost=0.1),
        _ev(model="claude-opus-4-8", cache_read=200, cost=0.1),
        _ev(model="claude-opus-4-8", cache_read=300, cost=0.1),
        _ev(model="claude-sonnet-4-5", cache_read=50, cost=0.05),
    ]
    by_model = {r["model"]: r for r in telemetry.efficiency(events)["by_model"]}
    assert by_model["claude-opus-4-8"]["calls"] == 3
    assert by_model["claude-opus-4-8"]["cache_read_per_call"] == round(600 / 3) == 200
    assert by_model["claude-sonnet-4-5"]["calls"] == 1
    assert by_model["claude-sonnet-4-5"]["cache_read_per_call"] == 50


def test_efficiency_rounding_is_banker_independent():
    # 100 + 101 over 2 calls -> 201/2 = 100.5; python round() -> 100 (round-half-to-even).
    events = [
        _ev(model="claude-opus-4-8", cache_read=100, cost=0.1),
        _ev(model="claude-opus-4-8", cache_read=101, cost=0.1),
    ]
    opus = telemetry.efficiency(events)["by_model"][0]
    assert opus["cache_read_per_call"] == round(201 / 2)


def test_efficiency_total_calls_and_cache_read_per_call_sum_across_models():
    events = [
        _ev(model="claude-opus-4-8", cache_read=100, cost=0.1),
        _ev(model="claude-opus-4-8", cache_read=300, cost=0.1),
        _ev(model="claude-sonnet-4-5", cache_read=600, cost=0.05),
    ]
    eff = telemetry.efficiency(events)
    total_calls = sum(r["calls"] for r in eff["by_model"])
    total_cr = sum(r["cache_read_tokens"] for r in eff["by_model"])
    t = eff["total"]
    assert t["calls"] == total_calls == 3
    assert t["cache_read_tokens"] == total_cr == 1000
    assert t["cache_read_per_call"] == round(1000 / 3)  # 333


def test_efficiency_empty_events_no_division_by_zero():
    eff = telemetry.efficiency([])
    assert eff["by_model"] == []
    assert eff["total"]["calls"] == 0
    assert eff["total"]["cache_read_per_call"] == 0


# --- by_skill -------------------------------------------------------------------------


def test_by_skill_grouping(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    rows = telemetry.by_skill(events)
    by_key = {r["key"]: r for r in rows}

    # e2 -> fenrir:deliver, e3 -> fenrir:ship, e1 + e4 -> (none) default label
    assert set(by_key) == {"fenrir:deliver", "fenrir:ship", "(none)"}
    assert by_key["fenrir:deliver"]["calls"] == 1
    assert by_key["fenrir:deliver"]["input_tokens"] == 2000
    assert by_key["fenrir:ship"]["calls"] == 1
    assert by_key["(none)"]["calls"] == 2  # e1 + e4 have no attributionSkill
    assert by_key["(none)"]["input_tokens"] == 1000 + 800


# --- by_source (main vs subagent) -----------------------------------------------------


def test_by_source_split(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    rows = telemetry.by_source(events)
    by_key = {r["key"]: r for r in rows}

    assert set(by_key) == {"main", "subagent"}
    # only e2 is sidechain -> subagent
    assert by_key["subagent"]["calls"] == 1
    assert by_key["subagent"]["input_tokens"] == 2000
    # main: e1, e3, e4
    assert by_key["main"]["calls"] == 3
    assert by_key["main"]["input_tokens"] == 1000 + 300 + 800


# --- by_day ---------------------------------------------------------------------------


def test_by_day_aggregation(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    rows = telemetry.by_day(events)
    by_day = {r["day"]: r for r in rows}

    assert list(by_day) == ["2026-06-01", "2026-06-02"]  # chronological
    # day 06-01: e1 (1000+200+500+100=1800) + e2 (2000+400=2400) = 4200
    assert by_day["2026-06-01"]["tokens"] == 1800 + 2400
    # day 06-02: e3 (300+50=350) + e4 (800+120=920) = 1270
    assert by_day["2026-06-02"]["tokens"] == 350 + 920
    assert all(r["cost_usd"] >= 0 for r in rows)


# --- agents combined view -------------------------------------------------------------


def test_agents_view(tmp_path):
    claude_dir = _build_tree(tmp_path)
    events = telemetry.load_events(claude_dir, PROJECT)
    view = telemetry.agents(events)
    assert set(view) == {"by_source", "by_skill"}
    assert {r["key"] for r in view["by_source"]} == {"main", "subagent"}
    assert "fenrir:deliver" in {r["key"] for r in view["by_skill"]}
