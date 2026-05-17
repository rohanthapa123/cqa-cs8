from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.routers.auth import get_current_user
from backend.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    BadPractice,
    FileBadPractices,
    FileComplexity,
    FileTimeComplexity,
    FunctionComplexity,
    FunctionTimeComplexity,
    SimilarityResult,
    TestCoverage,
)
from backend.services.analysis import analyze_repository

router = APIRouter(tags=["analysis"])


def _build_response(report: dict) -> AnalyzeResponse:
    cc = [
        FileComplexity(
            file_path=fp,
            functions=[
                FunctionComplexity(name=name, complexity=d["complexity"], lineno=d["lineno"])
                for name, d in funcs.items()
            ],
        )
        for fp, funcs in report["cyclomatic_complexity"].items()
    ]
    sim = [
        SimilarityResult(file_pair=pair.split("||"), similarity=score)
        for pair, score in report["similarity_matrix"].items()
    ]
    tc = [
        FileTimeComplexity(
            file_path=fp,
            functions=[
                FunctionTimeComplexity(
                    name=name,
                    lineno=d["lineno"],
                    complexity=d["complexity"],
                    is_recursive=d["is_recursive"],
                )
                for name, d in funcs.items()
            ],
        )
        for fp, funcs in report["time_complexity"].items()
    ]
    bp = [
        FileBadPractices(file_path=fp, issues=[BadPractice(**i) for i in issues])
        for fp, issues in report["bad_practices"].items()
        if issues
    ]
    tc_data = report["test_coverage"]
    tests = TestCoverage(**tc_data)
    return AnalyzeResponse(cyclomatic_complexity=cc, similarity_matrix=sim, time_complexity=tc, bad_practices=bp, test_coverage=tests)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, user=Depends(get_current_user)):
    try:
        report = analyze_repository(str(req.repo_url))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _build_response(report)


@router.post("/analyze/export")
async def export_report(result: AnalyzeResponse, user=Depends(get_current_user)):
    """Return analysis results as a downloadable Markdown report."""
    total_issues = sum(len(f.issues) for f in result.bad_practices)
    high_cc = sum(
        1 for f in result.cyclomatic_complexity for fn in f.functions if fn.complexity > 10
    )
    date = __import__("datetime").date.today().isoformat()

    lines = [
        "# CodeScope Analysis Report",
        f"**Generated:** {date}",
        "",
        "## Summary",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files analyzed | {len(result.cyclomatic_complexity)} |",
        f"| High-complexity functions (CC > 10) | {high_cc} |",
        f"| Duplicate file pairs | {len(result.similarity_matrix)} |",
        f"| Bad practice issues | {total_issues} |",
        "",
        "---",
        "",
        "## 1. Cyclomatic Complexity",
        "",
    ]

    for file in result.cyclomatic_complexity:
        fname = file.file_path.split("/")[-1]
        lines += [f"### {fname}", f"`{file.file_path}`"]
        if file.functions:
            lines += ["| Function | CC | Line |", "|----------|----|------|"]
            for fn in file.functions:
                flag = " ⚠️" if fn.complexity > 10 else (" ⚡" if fn.complexity > 5 else "")
                lines.append(f"| `{fn.name}` | {fn.complexity}{flag} | {fn.lineno} |")
        else:
            lines.append("_No functions found_")
        lines.append("")

    lines += ["---", "", "## 2. Duplicate Detection", ""]
    if result.similarity_matrix:
        lines += ["| File A | File B | Similarity |", "|--------|--------|-----------|"]
        for sim in result.similarity_matrix:
            a = sim.file_pair[0].split("/")[-1]
            b = sim.file_pair[1].split("/")[-1]
            lines.append(f"| `{a}` | `{b}` | {sim.similarity * 100:.1f}% |")
    else:
        lines.append("_Not enough files to compare_")

    lines += ["", "---", "", "## 3. Time Complexity", ""]
    for file in result.time_complexity:
        fname = file.file_path.split("/")[-1]
        lines.append(f"### {fname}")
        if file.functions:
            lines += ["| Function | Complexity | Recursive | Line |", "|----------|-----------|-----------|------|"]
            for fn in file.functions:
                lines.append(f"| `{fn.name}` | {fn.complexity} | {'Yes' if fn.is_recursive else 'No'} | {fn.lineno} |")
        else:
            lines.append("_No functions found_")
        lines.append("")

    lines += ["---", "", "## 4. Bad Practices", ""]
    files_with_issues = [f for f in result.bad_practices if f.issues]
    if files_with_issues:
        for file in files_with_issues:
            fname = file.file_path.split("/")[-1]
            lines.append(f"### {fname}")
            lines += ["| Line | Type | Message |", "|------|------|---------|"]
            for issue in file.issues:
                lines.append(f"| L{issue.line} | `{issue.type}` | {issue.message} |")
            lines.append("")
    else:
        lines.append("✅ No bad practices detected")

    lines += ["", "---", "_Generated by CodeScope_"]
    content = "\n".join(lines)

    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="codescope-report.md"'},
    )
