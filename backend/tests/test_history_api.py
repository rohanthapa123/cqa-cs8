"""End-to-end tests for the stored-history endpoints (/analyses/*)."""

import uuid

import pytest

from backend.models.analysis import Analysis
from backend.tests.conftest import TestingSessionLocal


def register(client) -> str:
    """Create a fresh user and return its bearer token."""
    unique = uuid.uuid4().hex[:8]
    response = client.post("/auth/signup", json={
        "email": f"trend-{unique}@example.com",
        "username": f"trend{unique}",
        "password": "correct-horse-battery",
    })
    assert response.status_code in (200, 201), response.text
    return response.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def user_id_for(token: str, client) -> int:
    return client.get("/auth/me", headers=auth(token)).json()["id"]


def seed_run(user_id: int, repo_name: str, health: int, **metric_overrides) -> int:
    """Insert a completed analysis run carrying a metric snapshot."""
    metrics = {
        "health_score": health, "average_maintainability": 70.0, "average_complexity": 3.0,
        "duplication_percentage": 5.0, "security_score": 90.0, "type_hint_coverage": 60.0,
        "high_risk_functions": 2, "critical_security_issues": 0, "dead_code_items": 4,
        "critical_hotspots": 1, "lines_of_code": 1000, "python_files": 20,
    }
    metrics.update(metric_overrides)

    db = TestingSessionLocal()
    try:
        run = Analysis(
            user_id=user_id,
            repo_name=repo_name,
            repo_url=f"https://github.com/demo/{repo_name}",
            status="completed",
            health_score=health,
            commit_sha="c" * 40,
        )
        run.metrics = metrics
        db.add(run)
        db.commit()
        return run.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# authentication
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/analyses", "/analyses/trend?repo_name=x", "/analyses/compare?base_id=1&head_id=2"])
def test_history_endpoints_require_authentication(client, path):
    assert client.get(path).status_code in (401, 403)


# ---------------------------------------------------------------------------
# listing
# ---------------------------------------------------------------------------

def test_lists_only_the_callers_runs(client):
    mine = register(client)
    theirs = register(client)
    seed_run(user_id_for(mine, client), "my-repo", 80)
    seed_run(user_id_for(theirs, client), "their-repo", 90)

    names = {r["repo_name"] for r in client.get("/analyses", headers=auth(mine)).json()}
    assert names == {"my-repo"}


def test_list_can_filter_by_repository(client):
    token = register(client)
    uid = user_id_for(token, client)
    seed_run(uid, "alpha", 80)
    seed_run(uid, "beta", 70)

    runs = client.get("/analyses", params={"repo_name": "beta"}, headers=auth(token)).json()
    assert [r["repo_name"] for r in runs] == ["beta"]


# ---------------------------------------------------------------------------
# trend series
# ---------------------------------------------------------------------------

def test_trend_returns_points_oldest_first(client):
    token = register(client)
    uid = user_id_for(token, client)
    seed_run(uid, "charted", 60)
    seed_run(uid, "charted", 75)
    seed_run(uid, "charted", 90)

    body = client.get("/analyses/trend", params={"repo_name": "charted"}, headers=auth(token)).json()
    assert body["run_count"] == 3
    assert [p["health_score"] for p in body["points"]] == [60, 75, 90]


def test_trend_includes_a_comparison_of_the_last_two_runs(client):
    token = register(client)
    uid = user_id_for(token, client)
    seed_run(uid, "declining", 90)
    seed_run(uid, "declining", 60)

    body = client.get("/analyses/trend", params={"repo_name": "declining"}, headers=auth(token)).json()
    assert body["latest_comparison"]["verdict"] == "regressed"


def test_trend_exposes_metric_definitions_for_charting(client):
    token = register(client)
    uid = user_id_for(token, client)
    seed_run(uid, "meta-repo", 80)

    body = client.get("/analyses/trend", params={"repo_name": "meta-repo"}, headers=auth(token)).json()
    keys = {m["key"] for m in body["metrics"]}
    assert {"health_score", "security_score", "type_hint_coverage"} <= keys
    assert any(m["higher_is_better"] is False for m in body["metrics"])


def test_trend_for_an_unknown_repository_is_empty(client):
    token = register(client)
    body = client.get("/analyses/trend", params={"repo_name": "nope"}, headers=auth(token)).json()
    assert body["run_count"] == 0
    assert body["latest_comparison"] is None


def test_failed_runs_are_excluded_from_the_chart(client):
    token = register(client)
    uid = user_id_for(token, client)
    seed_run(uid, "flaky", 80)

    db = TestingSessionLocal()
    try:
        db.add(Analysis(user_id=uid, repo_name="flaky",
                        repo_url="https://github.com/demo/flaky", status="failed"))
        db.commit()
    finally:
        db.close()

    body = client.get("/analyses/trend", params={"repo_name": "flaky"}, headers=auth(token)).json()
    assert body["run_count"] == 1


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------

def test_compare_two_runs(client):
    token = register(client)
    uid = user_id_for(token, client)
    base = seed_run(uid, "compared", 90, duplication_percentage=2.0)
    head = seed_run(uid, "compared", 70, duplication_percentage=9.0)

    body = client.get(
        "/analyses/compare", params={"base_id": base, "head_id": head}, headers=auth(token)
    ).json()

    assert body["verdict"] == "regressed"
    regressed = {c["metric"] for c in body["regressions"]}
    assert {"health_score", "duplication_percentage"} <= regressed


def test_compare_detects_improvement(client):
    token = register(client)
    uid = user_id_for(token, client)
    base = seed_run(uid, "improving", 60)
    head = seed_run(uid, "improving", 85)

    body = client.get(
        "/analyses/compare", params={"base_id": base, "head_id": head}, headers=auth(token)
    ).json()
    assert body["verdict"] == "improved"


def test_cannot_compare_another_users_runs(client):
    mine = register(client)
    theirs = register(client)
    base = seed_run(user_id_for(mine, client), "private", 80)
    head = seed_run(user_id_for(theirs, client), "private", 60)

    response = client.get(
        "/analyses/compare", params={"base_id": base, "head_id": head}, headers=auth(mine)
    )
    assert response.status_code == 404


def test_comparing_a_missing_run_is_404(client):
    token = register(client)
    uid = user_id_for(token, client)
    base = seed_run(uid, "solo", 80)

    response = client.get(
        "/analyses/compare", params={"base_id": base, "head_id": 999_999}, headers=auth(token)
    )
    assert response.status_code == 404
