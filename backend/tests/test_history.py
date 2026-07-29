from datetime import datetime, timedelta, timezone

import pytest
from git import Actor, Repo

from backend.services import history, trends


# ---------------------------------------------------------------------------
# a synthetic repository with a known commit history
# ---------------------------------------------------------------------------

ALICE = Actor("Alice", "alice@example.com")
BOB = Actor("Bob", "bob@example.com")


@pytest.fixture
def built_repo(tmp_path):
    """
    A repository with a deliberately lopsided history:

    - `hot.py`      changed in every commit, always by Alice  -> churn + bus factor 1
    - `paired_a/b`  always committed together                 -> change coupling
    - `calm.py`     touched once                              -> low churn
    """
    repo = Repo.init(tmp_path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def commit(index: int, author: Actor, files: dict):
        for name, body in files.items():
            (tmp_path / name).write_text(body)
            repo.index.add([name])
        # GitPython wants the offset without a colon (+0000, not +00:00).
        stamp = (base + timedelta(days=index)).strftime("%Y-%m-%dT%H:%M:%S%z")
        repo.index.commit(
            f"commit {index}",
            author=author, committer=author,
            author_date=stamp, commit_date=stamp,
        )

    commit(0, ALICE, {"hot.py": "x = 0\n", "calm.py": "y = 0\n"})
    for i in range(1, 7):
        files = {"hot.py": "x = 1\n" * i}
        if i % 2 == 0:
            files["paired_a.py"] = "a = %d\n" % i
            files["paired_b.py"] = "b = %d\n" % i
        commit(i, ALICE if i % 3 else BOB, files)

    return str(tmp_path)


COMPLEXITY = {"hot.py": 30, "calm.py": 1, "paired_a.py": 5, "paired_b.py": 5}


# ---------------------------------------------------------------------------
# parsing + availability
# ---------------------------------------------------------------------------

def test_reports_unavailable_outside_a_git_repository(tmp_path):
    report = history.analyze(str(tmp_path))
    assert report["available"] is False
    assert report["reason"]
    assert report["hotspots"] == []


def test_reports_unavailable_when_history_is_too_shallow(tmp_path):
    repo = Repo.init(tmp_path)
    (tmp_path / "only.py").write_text("x = 1\n")
    repo.index.add(["only.py"])
    repo.index.commit("single", author=ALICE, committer=ALICE)

    report = history.analyze(str(tmp_path))
    assert report["available"] is False
    assert "commit" in report["reason"]


def test_analyses_a_real_history(built_repo):
    report = history.analyze(built_repo, complexity_by_file=COMPLEXITY)
    assert report["available"] is True
    assert report["commits_analyzed"] == 7
    assert report["contributor_count"] == 2
    assert report["period_days"] == 6


def test_rename_paths_resolve_to_the_new_name():
    assert history._resolve_renamed_path("old.py => new.py") == "new.py"
    assert history._resolve_renamed_path("src/{old => new}/mod.py") == "src/new/mod.py"
    assert history._resolve_renamed_path("plain.py") == "plain.py"


# ---------------------------------------------------------------------------
# churn
# ---------------------------------------------------------------------------

def test_churn_ranks_the_most_edited_file_first(built_repo):
    report = history.analyze(built_repo, complexity_by_file=COMPLEXITY)
    assert report["churn_files"][0]["file_path"] == "hot.py"
    assert report["churn_files"][0]["commits"] == 7


def test_recent_commits_are_weighted_more_heavily():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recent = [{"author": "A", "date": now, "files": [("f.py", 10, 0)]}]
    old = [{"author": "A", "date": now - timedelta(days=history.CHURN_HALF_LIFE_DAYS),
            "files": [("f.py", 10, 0)]}]

    recent_weight = history.compute_churn(recent, now)["f.py"]["weighted_churn"]
    old_weight = history.compute_churn(old, now)["f.py"]["weighted_churn"]

    assert recent_weight == pytest.approx(10.0)
    assert old_weight == pytest.approx(5.0)  # exactly one half-life


# ---------------------------------------------------------------------------
# hotspots
# ---------------------------------------------------------------------------

def test_hotspot_needs_both_churn_and_complexity(built_repo):
    report = history.analyze(built_repo, complexity_by_file=COMPLEXITY)
    by_file = {h["file_path"]: h for h in report["hotspots"]}

    # hot.py is both complex and heavily churned -> top of the ranking.
    assert report["hotspots"][0]["file_path"] == "hot.py"
    # calm.py is trivial and barely touched -> negligible risk.
    assert by_file["calm.py"]["risk_score"] < by_file["hot.py"]["risk_score"]


def test_files_missing_from_the_snapshot_are_skipped(built_repo):
    # A file deleted before HEAD has churn but no current complexity.
    report = history.analyze(built_repo, complexity_by_file={"hot.py": 10})
    assert {h["file_path"] for h in report["hotspots"]} == {"hot.py"}


def test_risk_categories_follow_the_thresholds():
    assert history._categorise(0.60) == "critical"
    assert history._categorise(0.30) == "high"
    assert history._categorise(0.15) == "moderate"
    assert history._categorise(0.01) == "low"


def test_log_normalisation_dampens_the_long_tail():
    # A file with 100x the churn must not get 100x the score.
    assert history._normalise_churn(10_000, 10_000) == pytest.approx(1.0)
    assert history._normalise_churn(100, 10_000) > 0.5


# ---------------------------------------------------------------------------
# change coupling
# ---------------------------------------------------------------------------

def test_detects_files_that_always_change_together(built_repo):
    report = history.analyze(built_repo, complexity_by_file=COMPLEXITY)
    pairs = {tuple(sorted((c["file_a"], c["file_b"]))): c for c in report["coupling"]}
    assert ("paired_a.py", "paired_b.py") in pairs
    assert pairs[("paired_a.py", "paired_b.py")]["degree"] == 100.0


def test_sprawling_commits_are_excluded_from_coupling():
    # A commit touching everything would otherwise couple everything.
    paths = [f"f{i}.py" for i in range(history.MAX_FILES_PER_COMMIT_FOR_COUPLING + 5)]
    commits = [
        {"author": "A", "date": datetime(2026, 1, 1, tzinfo=timezone.utc),
         "files": [(p, 1, 0) for p in paths]}
        for _ in range(5)
    ]
    churn = history.compute_churn(commits, datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert history.compute_coupling(commits, churn) == []


def test_weak_coupling_is_filtered_out():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    commits = [{"author": "A", "date": now, "files": [("a.py", 1, 0), ("b.py", 1, 0)]}]
    churn = history.compute_churn(commits, now)
    # A single co-change is below MIN_COUPLING_SUPPORT.
    assert history.compute_coupling(commits, churn) == []


# ---------------------------------------------------------------------------
# bus factor
# ---------------------------------------------------------------------------

def test_bus_factor_counts_authors_covering_half_the_work():
    assert history._bus_factor({}) == 0
    assert history._bus_factor({"solo": 100}) == 1
    assert history._bus_factor({"a": 90, "b": 10}) == 1
    assert history._bus_factor({"a": 50, "b": 50}) == 1
    assert history._bus_factor({"a": 34, "b": 33, "c": 33}) == 2


def test_single_author_files_are_flagged_as_knowledge_risk(built_repo):
    report = history.analyze(built_repo, complexity_by_file=COMPLEXITY)
    bus = report["bus_factor"]
    assert bus["contributor_count"] == 2
    assert bus["repository_bus_factor"] >= 1
    assert {c["author"] for c in bus["top_contributors"]} == {"Alice", "Bob"}


def test_contributor_shares_sum_to_roughly_100(built_repo):
    report = history.analyze(built_repo, complexity_by_file=COMPLEXITY)
    total = sum(c["share"] for c in report["bus_factor"]["top_contributors"])
    assert total == pytest.approx(100.0, abs=0.5)


# ---------------------------------------------------------------------------
# trends + regression diffs
# ---------------------------------------------------------------------------

def snapshot(**overrides):
    base = {
        "health_score": 80, "average_maintainability": 70.0, "average_complexity": 3.0,
        "duplication_percentage": 5.0, "security_score": 90.0, "type_hint_coverage": 60.0,
        "high_risk_functions": 2, "critical_security_issues": 0, "dead_code_items": 4,
        "critical_hotspots": 1, "lines_of_code": 1000, "python_files": 20,
    }
    base.update(overrides)
    return base


def test_first_run_is_a_baseline_not_a_verdict():
    result = trends.compare(None, snapshot())
    assert result["available"] is False
    assert result["verdict"] == "baseline"
    assert result["changes"] == []


def test_identical_runs_are_unchanged():
    result = trends.compare(snapshot(), snapshot())
    assert result["verdict"] == "unchanged"
    assert result["regressions"] == []


def test_falling_health_score_is_a_regression():
    result = trends.compare(snapshot(health_score=80), snapshot(health_score=70))
    assert result["verdict"] == "regressed"
    assert [c["metric"] for c in result["regressions"]] == ["health_score"]


def test_rising_complexity_is_a_regression_but_rising_coverage_is_not():
    worse = trends.compare(snapshot(average_complexity=3.0), snapshot(average_complexity=5.0))
    better = trends.compare(snapshot(type_hint_coverage=60.0), snapshot(type_hint_coverage=80.0))
    assert worse["verdict"] == "regressed"
    assert better["verdict"] == "improved"


def test_movement_below_the_threshold_is_noise():
    result = trends.compare(snapshot(average_complexity=3.0), snapshot(average_complexity=3.1))
    assert result["verdict"] == "unchanged"


def test_size_metrics_have_no_good_direction():
    result = trends.compare(snapshot(lines_of_code=1000), snapshot(lines_of_code=2000))
    change = next(c for c in result["changes"] if c["metric"] == "lines_of_code")
    assert change["direction"] == "changed"
    assert result["verdict"] == "unchanged"


def test_percent_change_is_reported():
    result = trends.compare(snapshot(health_score=80), snapshot(health_score=40))
    change = next(c for c in result["changes"] if c["metric"] == "health_score")
    assert change["delta"] == -40.0
    assert change["percent_change"] == -50.0


def test_snapshot_is_built_from_a_full_report():
    report = {
        "summary": {
            "health_score": {"score": 77}, "average_maintainability": 65.0,
            "average_complexity": 4.2, "duplication_percentage": 8.0, "lines_of_code": 500,
            "python_files": 12,
        },
        "security": {"security_score": 55.0, "severity_counts": {"critical": 1, "high": 2}},
        "type_hints": {"coverage": 44.0},
        "complexity": {"high_risk_functions": [{}, {}, {}]},
        "dead_code": {"total_items": 9},
        "history": {"summary": {"critical_hotspots": 2}},
    }
    snap = trends.build_snapshot(report)
    assert snap["health_score"] == 77
    assert snap["critical_security_issues"] == 3
    assert snap["high_risk_functions"] == 3
    assert snap["critical_hotspots"] == 2


def test_series_orders_points_and_diffs_the_last_two():
    runs = [
        {"id": 1, "created_at": "2026-01-01T00:00:00", "commit_sha": "a" * 40,
         "metrics": snapshot(health_score=90)},
        {"id": 2, "created_at": "2026-01-02T00:00:00", "commit_sha": "b" * 40,
         "metrics": snapshot(health_score=70)},
    ]
    series = trends.build_series(runs)
    assert series["run_count"] == 2
    assert series["points"][0]["commit_sha"] == "aaaaaaa"
    assert series["latest_comparison"]["verdict"] == "regressed"


def test_empty_series_is_handled():
    series = trends.build_series([])
    assert series["run_count"] == 0
    assert series["latest_comparison"] is None
