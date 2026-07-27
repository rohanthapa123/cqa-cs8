"""
Maintainability analysis: Halstead metrics + Maintainability Index (MI).

Halstead metrics are derived from the counts of *operators* and *operands* in
the AST. The Maintainability Index combines the Halstead Volume, the
cyclomatic complexity and the lines of code into a single 0-100 score.

References:
    M. H. Halstead, "Elements of Software Science", 1977.
    Coleman, Ash, Lowther, Oman, "Using Metrics to Evaluate Software System
    Maintainability", IEEE Computer, 1994 (Maintainability Index).
"""

import ast
import math
from collections import Counter
from typing import Dict, List

# AST nodes treated as Halstead *operators* (keywords / actions), in addition
# to the arithmetic/boolean/comparison operator nodes handled generically.
_KEYWORD_OPERATORS = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith,
    ast.Return, ast.Break, ast.Continue, ast.Raise, ast.Assert, ast.Import,
    ast.ImportFrom, ast.Global, ast.Nonlocal, ast.Lambda, ast.Yield,
    ast.YieldFrom, ast.Await, ast.FunctionDef, ast.AsyncFunctionDef,
    ast.ClassDef, ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete,
    ast.Call, ast.Subscript, ast.comprehension, ast.IfExp,
)


def _halstead_counts(tree: ast.AST):
    operators: Counter = Counter()
    operands: Counter = Counter()

    for node in ast.walk(tree):
        if isinstance(node, (ast.operator, ast.unaryop, ast.boolop, ast.cmpop)):
            operators[type(node).__name__] += 1
        elif isinstance(node, _KEYWORD_OPERATORS):
            operators[type(node).__name__] += 1
        elif isinstance(node, ast.Name):
            operands[node.id] += 1
        elif isinstance(node, ast.arg):
            operands[node.arg] += 1
        elif isinstance(node, ast.Constant):
            operands[f"const:{node.value!r}"] += 1
        elif isinstance(node, ast.Attribute):
            operands[node.attr] += 1

    return operators, operands


def _halstead_metrics(source: str) -> Dict:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _empty_halstead()

    operators, operands = _halstead_counts(tree)

    n1 = len(operators)          # distinct operators
    n2 = len(operands)           # distinct operands
    N1 = sum(operators.values())  # total operators
    N2 = sum(operands.values())   # total operands

    vocabulary = n1 + n2
    length = N1 + N2
    volume = length * math.log2(vocabulary) if vocabulary > 0 else 0.0
    difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0.0
    effort = difficulty * volume

    return {
        "distinct_operators": n1,
        "distinct_operands": n2,
        "total_operators": N1,
        "total_operands": N2,
        "vocabulary": vocabulary,
        "length": length,
        "volume": round(volume, 2),
        "difficulty": round(difficulty, 2),
        "effort": round(effort, 2),
    }


def _empty_halstead() -> Dict:
    return {
        "distinct_operators": 0, "distinct_operands": 0,
        "total_operators": 0, "total_operands": 0,
        "vocabulary": 0, "length": 0,
        "volume": 0.0, "difficulty": 0.0, "effort": 0.0,
    }


def _rating(mi: float) -> str:
    if mi >= 80:
        return "Excellent"
    if mi >= 60:
        return "Good"
    if mi >= 40:
        return "Fair"
    return "Poor"


def analyze_file(file_path: str, source: str, cc_total: int, loc: int) -> Dict:
    """
    Compute Halstead metrics and the Maintainability Index for one file.

    MI uses the normalized (0-100) Coleman-Oman formula:
        MI = max(0, (171 - 5.2*ln(V) - 0.23*CC - 16.2*ln(LOC)) * 100 / 171)
    """
    halstead = _halstead_metrics(source)

    volume = max(halstead["volume"], 1.0)
    loc_safe = max(loc, 1)
    raw = 171 - 5.2 * math.log(volume) - 0.23 * cc_total - 16.2 * math.log(loc_safe)
    mi = max(0.0, min(100.0, raw * 100 / 171))
    mi = round(mi, 1)

    return {
        "file_path": file_path,
        "halstead": halstead,
        "cyclomatic_complexity": cc_total,
        "loc": loc,
        "maintainability_index": mi,
        "rating": _rating(mi),
    }


def summarize(file_reports: List[Dict]) -> Dict:
    """Aggregate per-file MI into repository-level statistics."""
    if not file_reports:
        return {"average_maintainability": 0.0, "rating": "Poor", "lowest_files": []}

    avg = round(sum(f["maintainability_index"] for f in file_reports) / len(file_reports), 1)
    lowest = sorted(file_reports, key=lambda f: f["maintainability_index"])[:5]

    return {
        "average_maintainability": avg,
        "rating": _rating(avg),
        "lowest_files": [
            {
                "file_path": f["file_path"],
                "maintainability_index": f["maintainability_index"],
                "rating": f["rating"],
            }
            for f in lowest
        ],
    }
