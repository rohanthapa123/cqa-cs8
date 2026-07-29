import hashlib
import hmac
import json

import pytest

from backend.core.config import settings
from backend.routers import webhooks

SECRET = "test-webhook-secret"


@pytest.fixture()
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", SECRET)
    return SECRET


def sign(payload: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def pull_request_event(action: str = "opened", draft: bool = False) -> dict:
    return {
        "action": action,
        "pull_request": {
            "number": 7,
            "draft": draft,
            "head": {"sha": "a" * 40},
        },
        "repository": {
            "full_name": "octocat/demo",
            "clone_url": "https://github.com/octocat/demo.git",
        },
    }


# ---------------------------------------------------------------------------
# signature verification
# ---------------------------------------------------------------------------

def test_valid_signature_is_accepted(webhook_secret):
    payload = b'{"action":"opened"}'
    assert webhooks.verify_signature(payload, sign(payload)) is True


def test_wrong_secret_is_rejected(webhook_secret):
    payload = b'{"action":"opened"}'
    assert webhooks.verify_signature(payload, sign(payload, "the-wrong-secret")) is False


def test_tampered_payload_is_rejected(webhook_secret):
    signature = sign(b'{"action":"opened"}')
    assert webhooks.verify_signature(b'{"action":"closed"}', signature) is False


def test_missing_or_malformed_signature_is_rejected(webhook_secret):
    payload = b"{}"
    assert webhooks.verify_signature(payload, None) is False
    assert webhooks.verify_signature(payload, "") is False
    assert webhooks.verify_signature(payload, "sha1=deadbeef") is False


def test_unset_secret_rejects_everything(monkeypatch):
    # Fail closed: without a configured secret, no delivery can be trusted.
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    payload = b"{}"
    assert webhooks.verify_signature(payload, sign(payload)) is False


# ---------------------------------------------------------------------------
# endpoint behaviour
# ---------------------------------------------------------------------------

def post_event(client, event: dict, secret: str = SECRET, github_event: str = "pull_request"):
    payload = json.dumps(event).encode()
    return client.post(
        "/webhooks/github",
        content=payload,
        headers={
            "X-Hub-Signature-256": sign(payload, secret),
            "X-GitHub-Event": github_event,
            "Content-Type": "application/json",
        },
    )


def test_endpoint_is_disabled_without_a_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    response = post_event(client, pull_request_event())
    assert response.status_code == 503


def test_bad_signature_is_unauthorized(client, webhook_secret):
    response = post_event(client, pull_request_event(), secret="wrong")
    assert response.status_code == 401


def test_ping_event_is_acknowledged(client, webhook_secret):
    response = post_event(client, {"zen": "hello"}, github_event="ping")
    assert response.status_code == 200
    assert response.json()["status"] == "pong"


def test_unhandled_event_type_is_ignored(client, webhook_secret):
    response = post_event(client, {"action": "created"}, github_event="issues")
    assert response.json()["status"] == "ignored"


def test_unhandled_action_is_ignored(client, webhook_secret):
    response = post_event(client, pull_request_event(action="closed"))
    assert response.json()["status"] == "ignored"


def test_draft_pull_requests_are_skipped(client, webhook_secret):
    response = post_event(client, pull_request_event(draft=True))
    assert response.json()["reason"] == "Pull request is a draft"


def test_malformed_payload_is_rejected(client, webhook_secret):
    event = pull_request_event()
    del event["repository"]["clone_url"]
    assert post_event(client, event).status_code == 400


def test_event_is_skipped_when_no_account_can_report(client, webhook_secret):
    # No user in the test database has connected the octocat GitHub account.
    response = post_event(client, pull_request_event())
    assert response.json()["status"] == "skipped"


# ---------------------------------------------------------------------------
# quality gate
# ---------------------------------------------------------------------------

def snapshot(**overrides):
    base = {"health_score": 80, "critical_security_issues": 0}
    base.update(overrides)
    return base


def comparison(changes=None, regressions=None):
    return {"available": True, "changes": changes or [], "regressions": regressions or []}


def health_change(before: float, after: float) -> dict:
    return {"metric": "health_score", "label": "Health score", "delta": after - before,
            "before": before, "after": after, "direction": "regressed"}


def test_clean_run_passes():
    state, description = webhooks.evaluate_gate(snapshot(), comparison())
    assert state == "success"
    assert "80" in description


def test_critical_security_issue_fails_the_gate():
    state, description = webhooks.evaluate_gate(
        snapshot(critical_security_issues=2), comparison()
    )
    assert state == "failure"
    assert "security" in description


def test_large_health_drop_fails_the_gate():
    state, description = webhooks.evaluate_gate(
        snapshot(health_score=60), comparison(changes=[health_change(80, 60)])
    )
    assert state == "failure"
    assert "Health score dropped" in description


def test_small_health_drop_passes_with_a_warning():
    change = health_change(80, 78)
    state, description = webhooks.evaluate_gate(
        snapshot(health_score=78), comparison(changes=[change], regressions=[change])
    )
    assert state == "success"
    assert "regression" in description


def test_baseline_run_with_no_comparison_passes():
    state, _ = webhooks.evaluate_gate(snapshot(), {"available": False, "verdict": "baseline"})
    assert state == "success"


# ---------------------------------------------------------------------------
# comment rendering
# ---------------------------------------------------------------------------

def build_report(**overrides):
    report = {
        "summary": {
            "health_score": {"score": 72, "grade": "B"},
            "average_complexity": 3.4,
            "duplication_percentage": 6.0,
            "average_maintainability": 61.0,
            "type_hint_coverage": 55.0,
            "dead_code_items": 3,
        },
        "security": {
            "security_score": 88.0,
            "severity_counts": {"critical": 0, "high": 1, "medium": 2, "low": 0},
            "files": [{
                "file_path": "app/db.py",
                "issues": [{"severity": "high", "title": "SQL query built by string interpolation", "line": 42}],
            }],
        },
        "complexity": {"high_risk_functions": [{}, {}]},
        "history": {"hotspots": [
            {"file_path": "app/core.py", "category": "critical", "risk_score": 61.2,
             "complexity": 48, "commits": 30},
        ]},
    }
    report.update(overrides)
    return report


def test_comment_includes_gate_verdict_and_metrics():
    body = webhooks.render_comment(
        build_report(), snapshot(), comparison(), "success", "Health score 72/100"
    )
    assert "CodeScope analysis" in body
    assert "PASSED" in body
    assert "72/100" in body
    assert "Type hint coverage" in body


def test_comment_lists_high_severity_findings_and_hotspots():
    body = webhooks.render_comment(build_report(), snapshot(), comparison(), "failure", "blocked")
    assert "FAILED" in body
    assert "app/db.py:42" in body
    assert "app/core.py" in body


def test_comment_renders_metric_deltas():
    change = {
        "metric": "duplication_percentage", "label": "Duplicate code", "unit": "%",
        "before": 4.0, "after": 6.0, "delta": 2.0, "direction": "regressed",
    }
    body = webhooks.render_comment(
        build_report(), snapshot(), comparison(changes=[change], regressions=[change]),
        "success", "ok",
    )
    assert "Duplicate code" in body
    assert "+2.0%" in body


def test_comment_explains_a_missing_baseline():
    body = webhooks.render_comment(
        build_report(), snapshot(),
        {"available": False, "verdict": "baseline", "reason": "First analysis of this repository."},
        "success", "ok",
    )
    assert "First analysis of this repository." in body


def test_comment_carries_the_sticky_marker_when_posted():
    # The marker is prepended by upsert_pr_comment, which is what makes the
    # comment update in place instead of stacking up on every push.
    assert webhooks.COMMENT_MARKER.startswith("<!--")
