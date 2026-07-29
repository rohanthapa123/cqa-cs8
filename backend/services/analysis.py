"""
Analysis orchestrator.

Coordinates every analysis module and produces the repository dashboard
summary and Overall Health Score.

Three *core* modules define the health score — Complexity, Duplication and
Maintainability — and are joined by supporting panels: Security, Dead code,
Type hints, behavioural git History (churn, hotspots, coupling, bus factor)
and the auxiliary Bad-practices linter.

Snapshot modules (everything driven by the AST) read from one shared
`(relative_path, source)` list so each file is read from disk exactly once.
The History module works from the commit log instead, and needs the clone to
carry real history — see `settings.history_clone_depth`.

Flow: clone → parse → measure → score → clean up.
"""

import ast
import os
import shutil
import tempfile
from typing import Dict, List, Optional, Tuple

from git import Repo

from backend.core.config import settings
from backend.services import (
    complexity,
    deadcode,
    duplication,
    history,
    maintainability,
    practices,
    security,
    typehints,
)

PYTHON_INDICATORS = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"}

# Overall Health Score weights (must sum to 1.0).
HEALTH_WEIGHTS = {"maintainability": 0.40, "complexity": 0.30, "duplication": 0.30}


# ---------------------------------------------------------------------------
# repo helpers
# ---------------------------------------------------------------------------

def clone_repo(github_url: str, ref: Optional[str] = None, depth: Optional[int] = None) -> str:
    """
    Shallow-clone a repository into a temporary directory.

    The clone is deep enough for behavioural analysis rather than `depth=1`:
    churn, hotspots, coupling and bus factor all need a commit log to read.

    `ref` fetches and checks out an arbitrary git ref — used by the PR
    integration to analyse `refs/pull/<n>/head`, which a plain clone of the
    default branch would never contain.
    """
    temp_dir = tempfile.mkdtemp(prefix="repo_clone_")
    depth = depth or settings.history_clone_depth
    try:
        repo = Repo.clone_from(github_url, temp_dir, depth=depth)
        if ref:
            repo.git.fetch("origin", ref, depth=depth)
            repo.git.checkout("FETCH_HEAD")
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone repository: {e}")
    return temp_dir


def head_commit(repo_path: str) -> Optional[str]:
    """SHA of the analysed commit, recorded so runs can be traced back to code."""
    try:
        return Repo(repo_path).head.commit.hexsha
    except Exception:
        return None


def is_python_project(root_dir: str) -> bool:
    for _, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(".py") or fname in PYTHON_INDICATORS:
                return True
    return False


def collect_python_files(root_dir: str) -> List[str]:
    py_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(os.path.join(dirpath, fname))
    return py_files


def _read(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ---------------------------------------------------------------------------
# per-file structural stats (LOC, functions, classes)
# ---------------------------------------------------------------------------

def file_stats(source: str) -> Dict[str, int]:
    """Source lines of code (excluding blanks/comment-only lines) + counts."""
    loc = 0
    for raw in source.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            loc += 1

    functions = classes = 0
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions += 1
            elif isinstance(node, ast.ClassDef):
                classes += 1
    except SyntaxError:
        pass

    return {"loc": loc, "functions": functions, "classes": classes}


# ---------------------------------------------------------------------------
# Overall Health Score
# ---------------------------------------------------------------------------

def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def compute_health_score(avg_maintainability: float, avg_complexity: float,
                         duplication_percentage: float) -> Dict:
    """
    Weighted 0-100 health score from the three core dimensions.

    - maintainability: the average MI (already 0-100)
    - complexity: 100 at avg CC <= 5, dropping to 0 by avg CC 25
    - duplication: 100 minus the duplication percentage
    """
    complexity_score = _clamp(100 - max(0.0, avg_complexity - 5) * 5)
    duplication_score = _clamp(100 - duplication_percentage)
    maintainability_score = _clamp(avg_maintainability)

    score = (
        HEALTH_WEIGHTS["maintainability"] * maintainability_score
        + HEALTH_WEIGHTS["complexity"] * complexity_score
        + HEALTH_WEIGHTS["duplication"] * duplication_score
    )

    if score >= 80:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": round(score),
        "grade": grade,
        "components": {
            "maintainability": round(maintainability_score),
            "complexity": round(complexity_score),
            "duplication": round(duplication_score),
        },
        "weights": HEALTH_WEIGHTS,
    }


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

def analyze_repository(github_url: str, ref: Optional[str] = None) -> Dict:
    repo_path = clone_repo(github_url, ref=ref)
    try:
        if not is_python_project(repo_path):
            raise ValueError("Not a Python project: no .py files or Python project files found")

        py_paths = collect_python_files(repo_path)

        # (rel_path, source) — read once, reuse across every module.
        files: List[Tuple[str, str]] = []
        for abs_path in py_paths:
            rel = os.path.relpath(abs_path, repo_path)
            files.append((rel, _read(abs_path)))

        stats_by_file = {rel: file_stats(src) for rel, src in files}
        loc_by_file = {rel: stats_by_file[rel]["loc"] for rel, _ in files}

        # --- core module 1: complexity ---
        complexity_files = [complexity.analyze_file(rel, src) for rel, src in files]
        complexity_summary = complexity.summarize(complexity_files)

        # --- core module 2: duplication (winnowing) ---
        duplication_report = duplication.analyze(files, loc_by_file)

        # --- core module 3: maintainability (Halstead + MI) ---
        cc_by_file = {f["file_path"]: f["total_complexity"] for f in complexity_files}
        maintainability_files = [
            maintainability.analyze_file(rel, src, cc_by_file.get(rel, 0), loc_by_file.get(rel, 0))
            for rel, src in files
        ]
        maintainability_summary = maintainability.summarize(maintainability_files)

        # --- repository totals (also feed the supporting modules below) ---
        total_functions = sum(s["functions"] for s in stats_by_file.values())
        total_classes = sum(s["classes"] for s in stats_by_file.values())
        total_loc = sum(s["loc"] for s in stats_by_file.values())

        # --- supporting module: security ---
        security_report = security.analyze(
            files, root_dir=repo_path, scan_deps=settings.enable_dependency_scan,
            total_loc=total_loc,
        )

        # --- supporting module: dead code ---
        dead_code_report = deadcode.analyze(files, total_loc=total_loc)

        # --- supporting module: type hint coverage ---
        type_hints_report = typehints.analyze(files)

        # --- supporting module: behavioural git history ---
        # Hotspots need per-file complexity to multiply churn against.
        history_report = history.analyze(repo_path, complexity_by_file=cc_by_file)

        # --- auxiliary: bad practices ---
        bad_practices = {rel: practices.detect(src) for rel, src in files}

        health = compute_health_score(
            maintainability_summary["average_maintainability"],
            complexity_summary["average_complexity"],
            duplication_report["duplication_percentage"],
        )

        repo_name = github_url.rstrip("/").split("/")[-1].replace(".git", "")

        summary = {
            "repository_name": repo_name,
            "python_files": len(files),
            "total_functions": total_functions,
            "total_classes": total_classes,
            "lines_of_code": total_loc,
            "average_complexity": complexity_summary["average_complexity"],
            "duplication_percentage": duplication_report["duplication_percentage"],
            "average_maintainability": maintainability_summary["average_maintainability"],
            "security_score": security_report["security_score"],
            "type_hint_coverage": type_hints_report["coverage"],
            "dead_code_items": dead_code_report["total_items"],
            "health_score": health,
        }

        return {
            "summary": summary,
            "commit_sha": head_commit(repo_path),
            "complexity": {
                "files": complexity_files,
                **complexity_summary,
            },
            "duplication": duplication_report,
            "maintainability": {
                "files": maintainability_files,
                **maintainability_summary,
            },
            "security": security_report,
            "dead_code": dead_code_report,
            "type_hints": type_hints_report,
            "history": history_report,
            "bad_practices": bad_practices,
        }
    finally:
        shutil.rmtree(repo_path, ignore_errors=True)
