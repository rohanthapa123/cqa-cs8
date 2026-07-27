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
from backend.services.analysis import analyze_repository

router = APIRouter(tags=["analysis"])


def _repo_name(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1].replace(".git", "")


def _record_analysis(db: Session, user_id: int, repo_url: str, status: str, health: int | None) -> None:
    """Best-effort persistence of an analysis run for admin monitoring."""
    try:
        db.add(Analysis(
            user_id=user_id,
            repo_name=_repo_name(repo_url),
            repo_url=repo_url,
            status=status,
            health_score=health,
        ))
        db.commit()
    except Exception:
        db.rollback()


def _build_response(report: dict) -> AnalyzeResponse:
    bad_practices = [
        FileBadPractices(file_path=fp, issues=[BadPractice(**i) for i in issues])
        for fp, issues in report["bad_practices"].items()
        if issues
    ]
    return AnalyzeResponse(
        summary=report["summary"],
        complexity=report["complexity"],
        duplication=report["duplication"],
        maintainability=report["maintainability"],
        bad_practices=bad_practices,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    repo_url = str(req.repo_url)
    try:
        report = analyze_repository(repo_url)
    except ValueError as e:
        _record_analysis(db, user.id, repo_url, "failed", None)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _record_analysis(db, user.id, repo_url, "failed", None)
        raise HTTPException(status_code=500, detail=str(e))
    _record_analysis(db, user.id, repo_url, "completed", report["summary"]["health_score"]["score"])
    return _build_response(report)


def _basename(path: str) -> str:
    return path.replace("\\", "/").split("/")[-1]


@router.post("/analyze/export")
async def export_report(result: AnalyzeResponse, user=Depends(get_current_user)):
    """Return analysis results as a downloadable Markdown report."""
    s = result.summary
    h = s.health_score
    date = __import__("datetime").date.today().isoformat()

    lines = [
        "# CodeScope Analysis Report",
        f"**Repository:** {s.repository_name}",
        f"**Generated:** {date}",
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
        "",
        "---",
        "",
        "## 1. Cyclomatic Complexity",
        f"Average CC **{result.complexity.average_complexity}** across "
        f"{result.complexity.function_count} functions.",
        "",
    ]

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
    content = "\n".join(lines)

    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="codescope-report.md"'},
    )
