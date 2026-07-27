"""
Cyclomatic Complexity analysis.

Uses Python's AST (via the `radon` library, which implements the McCabe
cyclomatic complexity metric on top of the standard `ast` module) to compute
the number of linearly independent paths through each function.

Reference:
    T. J. McCabe, "A Complexity Measure", IEEE Transactions on Software
    Engineering, SE-2(4), 1976.
"""

from typing import Dict, List

from radon.complexity import cc_visit

# A function with CC above this threshold is flagged as "high risk".
# McCabe's original recommendation is to keep modules at or below 10.
HIGH_RISK_THRESHOLD = 10


def analyze_file(file_path: str, source: str) -> Dict:
    """
    Compute cyclomatic complexity for every function/method in one file.

    Returns a dict with the per-function scores, the file-level average and
    total, and the list of high-risk functions.
    """
    try:
        blocks = cc_visit(source)
    except Exception:
        blocks = []

    functions: List[Dict] = [
        {
            "name": block.name,
            "complexity": block.complexity,
            "lineno": block.lineno,
            "is_high_risk": block.complexity > HIGH_RISK_THRESHOLD,
        }
        for block in blocks
    ]

    total = sum(fn["complexity"] for fn in functions)
    count = len(functions)
    average = round(total / count, 2) if count else 0.0
    max_complexity = max((fn["complexity"] for fn in functions), default=0)

    return {
        "file_path": file_path,
        "functions": functions,
        "average_complexity": average,
        "total_complexity": total,
        "max_complexity": max_complexity,
        "function_count": count,
    }


def summarize(file_reports: List[Dict]) -> Dict:
    """Aggregate per-file complexity into repository-level statistics."""
    all_functions = [fn for f in file_reports for fn in f["functions"]]
    total_functions = len(all_functions)
    total_complexity = sum(fn["complexity"] for fn in all_functions)
    average = round(total_complexity / total_functions, 2) if total_functions else 0.0

    high_risk = sorted(
        (
            {
                "name": fn["name"],
                "complexity": fn["complexity"],
                "lineno": fn["lineno"],
                "file_path": f["file_path"],
            }
            for f in file_reports
            for fn in f["functions"]
            if fn["is_high_risk"]
        ),
        key=lambda x: x["complexity"],
        reverse=True,
    )

    # Distribution used by the frontend to draw a small histogram/summary chart.
    distribution = {"low": 0, "moderate": 0, "high": 0}
    for fn in all_functions:
        if fn["complexity"] <= 5:
            distribution["low"] += 1
        elif fn["complexity"] <= HIGH_RISK_THRESHOLD:
            distribution["moderate"] += 1
        else:
            distribution["high"] += 1

    return {
        "average_complexity": average,
        "total_complexity": total_complexity,
        "function_count": total_functions,
        "high_risk_functions": high_risk,
        "distribution": distribution,
    }
