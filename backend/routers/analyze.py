from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.analysis import Analysis
from backend.routers.auth import get_current_user
from backend.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    BadPractice,
    FileBadPractices,
)
from backend.services import trends
from backend.services.analysis import analyze_repository

router = APIRouter(tags=["analysis"])


def _repo_name(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1].replace(".git", "")


def previous_run(db: Session, user_id: int, repo_name: str) -> Optional[Analysis]:
    """
    The most recent successful run of this repository, used as the diff base.

    Runs that predate metric snapshots are skipped — there is nothing in them
    to compare against.
    """
    return (
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


def _record_analysis(db: Session, user_id: int, repo_url: str, status: str,
                     health: Optional[int], commit_sha: Optional[str] = None,
                     metrics: Optional[dict] = None, ref: Optional[str] = None) -> None:
    """Best-effort persistence of an analysis run for monitoring and trends."""
    try:
        run = Analysis(
            user_id=user_id,
            repo_name=_repo_name(repo_url),
            repo_url=repo_url,
            status=status,
            health_score=health,
            commit_sha=commit_sha,
            ref=ref,
        )
        run.metrics = metrics
        db.add(run)
        db.commit()
    except Exception:
        db.rollback()


def _build_response(report: dict, comparison: Optional[dict] = None) -> AnalyzeResponse:
    bad_practices = [
        FileBadPractices(file_path=fp, issues=[BadPractice(**i) for i in issues])
        for fp, issues in report["bad_practices"].items()
        if issues
    ]
    return AnalyzeResponse(
        summary=report["summary"],
        commit_sha=report.get("commit_sha"),
        complexity=report["complexity"],
        duplication=report["duplication"],
        maintainability=report["maintainability"],
        security=report["security"],
        dead_code=report["dead_code"],
        type_hints=report["type_hints"],
        history=report["history"],
        bad_practices=bad_practices,
        comparison=comparison,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    repo_url = str(req.repo_url)

    # Read the diff base before inserting this run, or we would compare
    # the new run against itself.
    baseline = previous_run(db, user.id, _repo_name(repo_url))
    baseline_metrics = baseline.metrics if baseline else None

    try:
        report = analyze_repository(repo_url)
    except ValueError as e:
        _record_analysis(db, user.id, repo_url, "failed", None)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _record_analysis(db, user.id, repo_url, "failed", None)
        raise HTTPException(status_code=500, detail=str(e))

    snapshot = trends.build_snapshot(report)
    comparison = trends.compare(baseline_metrics, snapshot)

    _record_analysis(
        db, user.id, repo_url, "completed",
        report["summary"]["health_score"]["score"],
        commit_sha=report.get("commit_sha"),
        metrics=snapshot,
    )

    return _build_response(report, comparison)


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def _basename(path: str) -> str:
    return path.replace("\\", "/").split("/")[-1]


@router.post("/analyze/export")
async def export_report(result: AnalyzeResponse, user=Depends(get_current_user)):
    """Return analysis results as a downloadable Markdown report."""
    s = result.summary
    h = s.health_score

    lines = [
        "# CodeScope Analysis Report",
        f"**Repository:** {s.repository_name}",
        f"**Generated:** {date.today().isoformat()}",
    ]
    if result.commit_sha:
        lines.append(f"**Commit:** `{result.commit_sha[:10]}`")

    lines += [
        "",
        "## Overall Repository Health",
        f"**Health Score: {h.score}/100 (Grade {h.grade})**",
        "",
        "| Component | Score | Weight |",
        "|-----------|-------|--------|",
        f"| Maintainability | {h.components['maintainability']} | {int(h.weights['maintainability'] * 100)}% |",
        f"| Complexity | {h.components['complexity']} | {int(h.weights['complexity'] * 100)}% |",
        f"| Duplication | {h.components['duplication']} | {int(h.weights['duplication'] * 100)}% |",
        "",
        "## Summary",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Python files | {s.python_files} |",
        f"| Lines of code | {s.lines_of_code} |",
        f"| Total functions | {s.total_functions} |",
        f"| Total classes | {s.total_classes} |",
        f"| Average cyclomatic complexity | {s.average_complexity} |",
        f"| Duplicate code | {s.duplication_percentage}% |",
        f"| Average maintainability index | {s.average_maintainability} |",
        f"| Security score | {s.security_score}/100 |",
        f"| Type hint coverage | {s.type_hint_coverage}% |",
        f"| Dead code items | {s.dead_code_items} |",
        "",
    ]

    # --- change since the previous run ---
    comparison = result.comparison
    if comparison and comparison.available:
        lines += ["---", "", "## Change Since Previous Run",
                  f"**Verdict: {comparison.verdict.upper()}**", "",
                  "| Metric | Before | After | Change |", "|--------|--------|-------|--------|"]
        arrows = {"improved": "improved", "regressed": "regressed", "unchanged": "—", "changed": "changed"}
        for c in comparison.changes:
            if c.direction == "unchanged":
                continue
            sign = "+" if c.delta > 0 else ""
            lines.append(f"| {c.label} | {c.before}{c.unit} | {c.after}{c.unit} | "
                         f"{sign}{c.delta}{c.unit} ({arrows[c.direction]}) |")
        if not comparison.regressions:
            lines.append("")
            lines.append("_No regressions detected._")

    lines += ["", "---", "", "## 1. Cyclomatic Complexity",
              f"Average CC **{result.complexity.average_complexity}** across "
              f"{result.complexity.function_count} functions.", ""]

    if result.complexity.high_risk_functions:
        lines += ["### High-risk functions (CC > 10)", "",
                  "| Function | File | CC | Line |", "|----------|------|----|------|"]
        for fn in result.complexity.high_risk_functions:
            lines.append(f"| `{fn.name}` | {_basename(fn.file_path)} | {fn.complexity} | {fn.lineno} |")
    else:
        lines.append("_No high-risk functions._")

    lines += ["", "---", "", "## 2. Duplicate Code Detection (Winnowing)",
              f"Overall duplication: **{result.duplication.duplication_percentage}%** "
              f"({result.duplication.duplicated_lines}/{result.duplication.total_lines} lines).", ""]
    if result.duplication.duplicate_pairs:
        lines += ["| File A | File B | Similarity | Duplicate ranges (A) |",
                  "|--------|--------|-----------|----------------------|"]
        for p in result.duplication.duplicate_pairs:
            ranges = ", ".join(f"{b.start}-{b.end}" for b in p.blocks_a) or "—"
            lines.append(f"| `{_basename(p.file_a)}` | `{_basename(p.file_b)}` | {p.similarity}% | {ranges} |")
    else:
        lines.append("_No significant duplication detected._")

    lines += ["", "---", "", "## 3. Maintainability (Halstead + MI)",
              f"Average Maintainability Index: **{result.maintainability.average_maintainability}** "
              f"({result.maintainability.rating}).", ""]
    if result.maintainability.lowest_files:
        lines += ["### Lowest-maintainability files", "",
                  "| File | MI | Rating |", "|------|----|--------|"]
        for f in result.maintainability.lowest_files:
            lines.append(f"| `{_basename(f.file_path)}` | {f.maintainability_index} | {f.rating} |")

    # --- security ---
    sec = result.security
    counts = sec.severity_counts
    lines += ["", "---", "", "## 4. Security",
              f"Security score: **{sec.security_score}/100** — {sec.total_issues} issue(s) across "
              f"{sec.affected_files} file(s).", "",
              f"Critical: {counts.get('critical', 0)} · High: {counts.get('high', 0)} · "
              f"Medium: {counts.get('medium', 0)} · Low: {counts.get('low', 0)}", ""]

    if sec.files:
        lines += ["### Code findings", "", "| Severity | File | Line | Issue | CWE |",
                  "|----------|------|------|-------|-----|"]
        for file in sec.files:
            for issue in file.issues:
                lines.append(f"| {issue.severity} | `{_basename(file.file_path)}` | L{issue.line} | "
                             f"{issue.title} | {issue.cwe or '—'} |")
    else:
        lines.append("_No code-level security findings._")

    deps = sec.dependencies
    lines += ["", "### Dependency vulnerabilities", ""]
    if not deps.available:
        lines.append(f"_{deps.reason}_")
    elif deps.vulnerabilities:
        lines += [f"{len(deps.vulnerabilities)} advisory(ies) affecting "
                  f"{deps.vulnerable_package_count} of {deps.dependencies_checked} pinned packages.", "",
                  "| Severity | Package | Version | Advisory | Fixed in |",
                  "|----------|---------|---------|----------|----------|"]
        for v in deps.vulnerabilities:
            fixed = ", ".join(v.fixed_versions) or "—"
            lines.append(f"| {v.severity} | `{v.package}` | {v.version} | "
                         f"{v.cve or v.vulnerability_id} | {fixed} |")
    else:
        lines.append(f"_No known vulnerabilities in {deps.dependencies_checked} pinned package(s)._")

    # --- dead code ---
    dead = result.dead_code
    lines += ["", "---", "", "## 5. Dead Code",
              f"{dead.total_items} item(s), covering {dead.dead_lines} line(s) "
              f"({dead.dead_code_percentage}% of the codebase).", "",
              "| Category | Count |", "|----------|-------|"]
    for key, label in [("dead_functions", "Unreferenced functions"),
                       ("dead_classes", "Unreferenced classes"),
                       ("unused_imports", "Unused imports"),
                       ("unused_locals", "Unused local variables"),
                       ("unreachable_code", "Unreachable statements")]:
        lines.append(f"| {label} | {dead.counts.get(key, 0)} |")

    unreferenced = [*dead.dead_functions, *dead.dead_classes]
    if unreferenced:
        lines += ["", "### Unreferenced definitions", "",
                  "| Name | Kind | File | Line | Lines | Confidence |",
                  "|------|------|------|------|-------|------------|"]
        for d in unreferenced:
            lines.append(f"| `{d.name}` | {d.kind} | {_basename(d.file_path)} | {d.lineno} | "
                         f"{d.lines} | {d.confidence} |")

    # --- type hints ---
    th = result.type_hints
    lines += ["", "---", "", "## 6. Type Hint Coverage",
              f"Coverage: **{th.coverage}%** ({th.rating}) — {th.annotated_slots} of "
              f"{th.total_slots} annotatable slots.", "",
              f"Fully typed: {th.fully_typed} · Partially typed: {th.partially_typed} · "
              f"Untyped: {th.untyped} (of {th.function_count} functions)", ""]
    if th.lowest_files:
        lines += ["### Least-annotated files", "", "| File | Coverage | Functions | Untyped |",
                  "|------|----------|-----------|---------|"]
        for f in th.lowest_files:
            lines.append(f"| `{_basename(f.file_path)}` | {f.coverage}% | {f.function_count} | {f.untyped} |")

    # --- behavioural history ---
    hist = result.history
    lines += ["", "---", "", "## 7. Behavioural Analysis (git history)", ""]
    if not hist.available:
        lines.append(f"_{hist.reason}_")
    else:
        lines += [f"{hist.commits_analyzed} commits from {hist.contributor_count} contributor(s) "
                  f"over {hist.period_days} days ({hist.first_commit} to {hist.last_commit}).", ""]

        if hist.hotspots:
            lines += ["### Hotspots (churn x complexity)", "",
                      "| File | Risk | Category | Complexity | Churn | Commits |",
                      "|------|------|----------|------------|-------|---------|"]
            for hs in hist.hotspots:
                lines.append(f"| `{_basename(hs.file_path)}` | {hs.risk_score} | {hs.category} | "
                             f"{hs.complexity} | {hs.churn} | {hs.commits} |")

        if hist.churn_files:
            lines += ["", "### Most-changed files", "",
                      "| File | Commits | +Lines | -Lines | Authors |",
                      "|------|---------|--------|--------|---------|"]
            for cf in hist.churn_files[:15]:
                lines.append(f"| `{_basename(cf.file_path)}` | {cf.commits} | {cf.insertions} | "
                             f"{cf.deletions} | {cf.author_count} |")

        if hist.coupling:
            lines += ["", "### Change coupling", "",
                      "| File A | File B | Co-changes | Degree |",
                      "|--------|--------|-----------|--------|"]
            for c in hist.coupling:
                lines.append(f"| `{_basename(c.file_a)}` | `{_basename(c.file_b)}` | "
                             f"{c.co_changes} | {c.degree}% |")

        bf = hist.bus_factor
        lines += ["", "### Knowledge distribution",
                  f"Repository bus factor: **{bf.repository_bus_factor}** "
                  f"({bf.contributor_count} contributors, {bf.at_risk_count} file(s) with concentrated ownership).", ""]
        if bf.top_contributors:
            lines += ["| Contributor | Commits | Lines | Share |", "|-------------|---------|-------|-------|"]
            for c in bf.top_contributors[:10]:
                lines.append(f"| {c.author} | {c.commits} | {c.lines} | {c.share}% |")
        if bf.at_risk_files:
            lines += ["", "#### Files with concentrated ownership", "",
                      "| File | Primary author | Share | Authors |",
                      "|------|----------------|-------|---------|"]
            for f in bf.at_risk_files[:10]:
                lines.append(f"| `{_basename(f.file_path)}` | {f.primary_author} | "
                             f"{f.primary_author_share}% | {f.author_count} |")

    # --- auxiliary ---
    lines += ["", "---", "", "## Bad Practices (auxiliary)", ""]
    files_with_issues = [f for f in result.bad_practices if f.issues]
    if files_with_issues:
        for file in files_with_issues:
            lines.append(f"### {_basename(file.file_path)}")
            lines += ["| Line | Type | Message |", "|------|------|---------|"]
            for issue in file.issues:
                lines.append(f"| L{issue.line} | `{issue.type}` | {issue.message} |")
            lines.append("")
    else:
        lines.append("No bad practices detected.")

    lines += ["", "---", "_Generated by CodeScope_"]

    return Response(
        content="\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="codescope-report.md"'},
    )
