"""
GitHub pull-request integration.

Turns the analyzer from a dashboard you visit into a check that runs itself.
On every push to an open pull request GitHub delivers a `pull_request` event
here, and the backend:

1. verifies the delivery's HMAC signature,
2. marks the head commit's status as *pending* so the PR shows work in flight,
3. analyses the PR head (`refs/pull/<n>/head`) off the request thread,
4. diffs it against the repository's last completed run,
5. posts — or updates in place — a single sticky comment with the deltas, and
6. resolves the commit status to success or failure via the quality gate.

Webhooks cannot reach a laptop, so `POST /webhooks/pull-request/check` runs the
identical pipeline on demand for a repo and PR number. That is the path to use
in local development.

Delivery must be fast: GitHub abandons a webhook that takes longer than about
ten seconds, and a full clone-and-analyse takes far longer than that. The
handler therefore validates, acknowledges, and hands the real work to a
background task.
"""

import hashlib
import hmac
from typing import Dict, Optional, Tuple

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.database import SessionLocal, get_db
from backend.models.analysis import Analysis
from backend.models.user import User
from backend.routers.auth import get_current_user
from backend.services import trends
from backend.services.analysis import analyze_repository

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

GITHUB_API_URL = "https://api.github.com"

# Marker hidden in the comment body so repeated pushes update one comment
# instead of burying the PR under a new one each time.
COMMENT_MARKER = "<!-- codescope-analysis-report -->"

STATUS_CONTEXT = "codescope/analysis"

HANDLED_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}

# --- quality gate -----------------------------------------------------------
# A pull request fails the gate on either of these. Everything else is
# reported in the comment but does not block.

MAX_HEALTH_SCORE_DROP = 5.0     # points of the 0-100 health score
ALLOWED_CRITICAL_ISSUES = 0     # new critical/high security findings


# ---------------------------------------------------------------------------
# signature verification
# ---------------------------------------------------------------------------

def verify_signature(payload: bytes, signature: Optional[str]) -> bool:
    """
    Constant-time HMAC-SHA256 check of `X-Hub-Signature-256`.

    Without this anyone who learns the URL could post a forged event, so an
    unset secret disables the endpoint outright rather than accepting
    everything.
    """
    if not settings.github_webhook_secret:
        return False
    if not signature or not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature[len("sha256="):])


# ---------------------------------------------------------------------------
# GitHub API calls
# ---------------------------------------------------------------------------

def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def set_commit_status(token: str, repo_full_name: str, sha: str, state: str,
                      description: str, target_url: Optional[str] = None) -> None:
    """
    Publish a commit status, which is what renders as a check on the PR.

    Best-effort: a failure to report must never fail the analysis itself.
    """
    try:
        with httpx.Client(timeout=15.0) as client:
            client.post(
                f"{GITHUB_API_URL}/repos/{repo_full_name}/statuses/{sha}",
                headers=_headers(token),
                json={
                    "state": state,                     # pending | success | failure | error
                    "context": STATUS_CONTEXT,
                    "description": description[:140],   # GitHub truncates at 140
                    **({"target_url": target_url} if target_url else {}),
                },
            )
    except Exception:
        pass


def upsert_pr_comment(token: str, repo_full_name: str, pr_number: int, body: str) -> None:
    """Post the report comment, or edit the existing one if we already left it."""
    body = f"{COMMENT_MARKER}\n{body}"
    try:
        with httpx.Client(timeout=20.0) as client:
            existing = client.get(
                f"{GITHUB_API_URL}/repos/{repo_full_name}/issues/{pr_number}/comments",
                headers=_headers(token),
                params={"per_page": 100},
            )
            if existing.status_code == 200:
                for comment in existing.json():
                    if COMMENT_MARKER in (comment.get("body") or ""):
                        client.patch(
                            f"{GITHUB_API_URL}/repos/{repo_full_name}/issues/comments/{comment['id']}",
                            headers=_headers(token),
                            json={"body": body},
                        )
                        return

            client.post(
                f"{GITHUB_API_URL}/repos/{repo_full_name}/issues/{pr_number}/comments",
                headers=_headers(token),
                json={"body": body},
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# quality gate + comment rendering
# ---------------------------------------------------------------------------

def evaluate_gate(snapshot: Dict, comparison: Dict) -> Tuple[str, str]:
    """
    Decide the commit status from the run and its diff against the base.

    Only two things block a merge: a critical or high severity security finding,
    and a material drop in the health score. Smaller regressions are surfaced in
    the comment so the author sees them without the build going red over noise.
    """
    critical = snapshot.get("critical_security_issues", 0)
    if critical > ALLOWED_CRITICAL_ISSUES:
        return "failure", f"{critical} critical/high security issue(s) found"

    health_change = next(
        (c for c in comparison.get("changes", []) if c["metric"] == "health_score"),
        None,
    )
    if health_change and health_change["delta"] <= -MAX_HEALTH_SCORE_DROP:
        return "failure", (
            f"Health score dropped {abs(health_change['delta'])} points "
            f"({health_change['before']} to {health_change['after']})"
        )

    regressions = comparison.get("regressions", [])
    if regressions:
        return "success", f"Passed with {len(regressions)} regression(s) — see the PR comment"

    return "success", f"Health score {snapshot.get('health_score', 0)}/100"


def render_comment(report: Dict, snapshot: Dict, comparison: Dict,
                   gate_state: str, gate_description: str) -> str:
    """Build the Markdown body posted to the pull request."""
    summary = report["summary"]
    health = summary["health_score"]
    security = report["security"]
    verdict_icon = {"success": "PASSED", "failure": "FAILED"}.get(gate_state, "CHECKED")

    lines = [
        "## CodeScope analysis",
        "",
        f"**Quality gate: {verdict_icon}** — {gate_description}",
        "",
        f"**Health score: {health['score']}/100 (grade {health['grade']})**",
        "",
    ]

    if comparison.get("available"):
        changed = [c for c in comparison["changes"] if c["direction"] != "unchanged"]
        if changed:
            lines += ["### Changes since the last analysis", "",
                      "| Metric | Before | After | Change |",
                      "|--------|--------|-------|--------|"]
            for c in changed:
                sign = "+" if c["delta"] > 0 else ""
                note = {"improved": " ✅", "regressed": " ⚠️"}.get(c["direction"], "")
                lines.append(
                    f"| {c['label']} | {c['before']}{c['unit']} | {c['after']}{c['unit']} "
                    f"| {sign}{c['delta']}{c['unit']}{note} |"
                )
            lines.append("")
        else:
            lines += ["_No measurable change against the previous run._", ""]
    else:
        lines += [f"_{comparison.get('reason', 'No baseline to compare against.')}_", ""]

    counts = security["severity_counts"]
    lines += [
        "### Current state",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Security score | {security['security_score']}/100 |",
        f"| Security findings | {counts.get('critical', 0)} critical · {counts.get('high', 0)} high "
        f"· {counts.get('medium', 0)} medium · {counts.get('low', 0)} low |",
        f"| Average complexity | {summary['average_complexity']} |",
        f"| High-risk functions | {len(report['complexity']['high_risk_functions'])} |",
        f"| Duplication | {summary['duplication_percentage']}% |",
        f"| Maintainability index | {summary['average_maintainability']} |",
        f"| Type hint coverage | {summary['type_hint_coverage']}% |",
        f"| Dead code items | {summary['dead_code_items']} |",
        "",
    ]

    blocking = [
        issue
        for file in security["files"]
        for issue in file["issues"]
        if issue["severity"] in ("critical", "high")
    ][:10]
    if blocking:
        lines += ["### Security findings requiring attention", "",
                  "| Severity | Issue | Location |", "|----------|-------|----------|"]
        for file in security["files"]:
            for issue in file["issues"]:
                if issue["severity"] not in ("critical", "high"):
                    continue
                lines.append(
                    f"| {issue['severity']} | {issue['title']} | `{file['file_path']}:{issue['line']}` |"
                )
        lines.append("")

    hotspots = report.get("history", {}).get("hotspots", [])
    top_hotspots = [h for h in hotspots if h["category"] in ("critical", "high")][:5]
    if top_hotspots:
        lines += ["### Hotspots in this repository", "",
                  "| File | Risk | Complexity | Commits |", "|------|------|------------|---------|"]
        for h in top_hotspots:
            lines.append(f"| `{h['file_path']}` | {h['risk_score']} | {h['complexity']} | {h['commits']} |")
        lines.append("")

    lines += ["<sub>Posted by CodeScope. This comment updates in place on every push.</sub>"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# the analysis job
# ---------------------------------------------------------------------------

def run_pr_analysis(user_id: int, token: str, repo_full_name: str, clone_url: str,
                    pr_number: int, head_sha: str) -> None:
    """
    Analyse a pull request head and report back to GitHub.

    Runs off the request thread with its own database session, since the
    request-scoped one is already closed by the time this executes.
    """
    set_commit_status(token, repo_full_name, head_sha, "pending", "Analysing pull request...")

    db: Session = SessionLocal()
    try:
        repo_name = repo_full_name.split("/")[-1]
        baseline = (
            db.query(Analysis)
            .filter(
                Analysis.user_id == user_id,
                Analysis.repo_name == repo_name,
                Analysis.status == "completed",
                Analysis.metrics_json.isnot(None),
            )
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .first()
        )
        baseline_metrics = baseline.metrics if baseline else None

        try:
            report = analyze_repository(clone_url, ref=f"refs/pull/{pr_number}/head")
        except Exception as e:
            set_commit_status(token, repo_full_name, head_sha, "error", f"Analysis failed: {e}")
            upsert_pr_comment(
                token, repo_full_name, pr_number,
                f"## CodeScope analysis\n\nThe analysis could not be completed.\n\n```\n{e}\n```",
            )
            db.add(Analysis(
                user_id=user_id, repo_name=repo_name, repo_url=clone_url,
                status="failed", commit_sha=head_sha, ref=f"pull/{pr_number}",
            ))
            db.commit()
            return

        snapshot = trends.build_snapshot(report)
        comparison = trends.compare(baseline_metrics, snapshot)
        gate_state, gate_description = evaluate_gate(snapshot, comparison)

        run = Analysis(
            user_id=user_id,
            repo_name=repo_name,
            repo_url=clone_url,
            status="completed",
            health_score=report["summary"]["health_score"]["score"],
            commit_sha=head_sha,
            ref=f"pull/{pr_number}",
        )
        run.metrics = snapshot
        db.add(run)
        db.commit()

        upsert_pr_comment(
            token, repo_full_name, pr_number,
            render_comment(report, snapshot, comparison, gate_state, gate_description),
        )
        set_commit_status(token, repo_full_name, head_sha, gate_state, gate_description)
    except Exception as e:
        db.rollback()
        set_commit_status(token, repo_full_name, head_sha, "error", f"Analysis failed: {e}")
    finally:
        db.close()


def resolve_actor(db: Session, repo_full_name: str) -> Optional[User]:
    """
    Find a connected account whose token can write to this repository.

    Preference order: the repository owner if they have connected GitHub here,
    otherwise whoever last analysed this repository through the dashboard.
    """
    owner_login = repo_full_name.split("/")[0]

    user = (
        db.query(User)
        .filter(User.github_username == owner_login, User.github_access_token.isnot(None))
        .first()
    )
    if user:
        return user

    run = (
        db.query(Analysis)
        .filter(Analysis.repo_name == repo_full_name.split("/")[-1])
        .order_by(Analysis.created_at.desc())
        .first()
    )
    if run:
        candidate = db.query(User).filter(
            User.id == run.user_id, User.github_access_token.isnot(None)
        ).first()
        if candidate:
            return candidate

    return None


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------

@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Receive GitHub webhook deliveries and queue pull-request analyses."""
    payload = await request.body()

    if not settings.github_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook endpoint disabled: GITHUB_WEBHOOK_SECRET is not configured.",
        )
    if not verify_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Event '{x_github_event}' is not handled"}

    event = await request.json()
    action = event.get("action")
    if action not in HANDLED_ACTIONS:
        return {"status": "ignored", "reason": f"Action '{action}' is not handled"}

    pull_request = event.get("pull_request", {})
    repository = event.get("repository", {})

    if pull_request.get("draft"):
        return {"status": "ignored", "reason": "Pull request is a draft"}

    repo_full_name = repository.get("full_name")
    clone_url = repository.get("clone_url")
    pr_number = pull_request.get("number")
    head_sha = pull_request.get("head", {}).get("sha")

    if not all([repo_full_name, clone_url, pr_number, head_sha]):
        raise HTTPException(status_code=400, detail="Malformed pull_request payload")

    actor = resolve_actor(db, repo_full_name)
    if not actor:
        return {
            "status": "skipped",
            "reason": f"No connected account can post results to {repo_full_name}",
        }

    background_tasks.add_task(
        run_pr_analysis,
        actor.id, actor.github_access_token, repo_full_name, clone_url, pr_number, head_sha,
    )
    return {"status": "queued", "repository": repo_full_name, "pull_request": pr_number}


@router.post("/pull-request/check")
async def check_pull_request(
    repo_full_name: str,
    pr_number: int,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """
    Run the pull-request pipeline on demand.

    The same code path as the webhook, triggered manually — which is how you
    exercise it from a machine GitHub cannot deliver webhooks to.
    """
    if not user.github_access_token:
        raise HTTPException(status_code=400, detail="GitHub account not connected")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{GITHUB_API_URL}/repos/{repo_full_name}/pulls/{pr_number}",
            headers=_headers(user.github_access_token),
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Pull request {repo_full_name}#{pr_number} not found")
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error ({response.status_code}): {response.text[:200]}",
        )

    pull_request = response.json()
    head_sha = pull_request["head"]["sha"]
    clone_url = pull_request["base"]["repo"]["clone_url"]

    background_tasks.add_task(
        run_pr_analysis,
        user.id, user.github_access_token, repo_full_name, clone_url, pr_number, head_sha,
    )
    return {
        "status": "queued",
        "repository": repo_full_name,
        "pull_request": pr_number,
        "head_sha": head_sha,
    }
