"""
Pull-request reporting: the quality gate and the Markdown comment body.

Kept separate from `routers/webhooks.py` so both consumers can share it — the
webhook, which posts from the running backend, and `backend/cli.py`, which runs
inside GitHub Actions where FastAPI and a database are not available. These are
pure functions over analysis output; nothing here touches the network.
"""

from typing import Dict, Tuple

# --- quality gate -----------------------------------------------------------
# A pull request fails the gate on either of these. Everything else is
# reported in the comment but does not block.

MAX_HEALTH_SCORE_DROP = 5.0     # points of the 0-100 health score
ALLOWED_CRITICAL_ISSUES = 0     # critical/high severity security findings


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
