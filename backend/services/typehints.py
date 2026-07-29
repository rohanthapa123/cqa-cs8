"""
Type hint coverage.

Measures how much of the codebase carries PEP 484 annotations. Every function
contributes a number of *annotatable slots* — one per parameter plus one for
the return type — and coverage is the fraction of those slots that are filled.

`self` and `cls` are excluded: annotating them is neither conventional nor
useful, so counting them would permanently cap every class-heavy project below
100%. Overload stubs and `__init__`'s `-> None` are counted normally.

Alongside the ratio, three counts are reported because they mean different
things to a reader: *fully typed* functions can be checked end-to-end by mypy,
*partially typed* ones give it something to work with, and *untyped* ones are
invisible to it.
"""

import ast
from typing import Dict, List, Sequence, Tuple

# Parameters that are never annotated by convention.
IMPLICIT_PARAMETERS = {"self", "cls"}

# Coverage bands, mirroring the maintainability module's rating vocabulary.
RATING_THRESHOLDS = [(90.0, "Excellent"), (70.0, "Good"), (40.0, "Fair")]

MAX_LISTED_FILES = 20
MAX_LISTED_FUNCTIONS = 30


def rate(coverage: float) -> str:
    for threshold, label in RATING_THRESHOLDS:
        if coverage >= threshold:
            return label
    return "Poor"


def _annotatable_parameters(node: ast.AST) -> List[ast.arg]:
    """Every parameter of a function that a reader would expect to be annotated."""
    args = node.args
    parameters: List[ast.arg] = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            parameters.append(extra)
    return [p for p in parameters if p.arg not in IMPLICIT_PARAMETERS]


def analyze_file(file_path: str, source: str) -> Dict:
    """Annotation coverage for one file, plus the functions that lack hints."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {
            "file_path": file_path,
            "functions": [],
            "function_count": 0,
            "annotated_slots": 0,
            "total_slots": 0,
            "coverage": 0.0,
            "fully_typed": 0,
            "partially_typed": 0,
            "untyped": 0,
            "annotated_variables": 0,
            "rating": "Poor",
        }

    # Methods need their owning class for a readable label in the report.
    owners: Dict[int, str] = {}
    for parent in ast.walk(tree):
        if isinstance(parent, ast.ClassDef):
            for child in ast.iter_child_nodes(parent):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    owners[id(child)] = parent.name

    functions: List[Dict] = []
    annotated_slots = total_slots = 0
    fully_typed = partially_typed = untyped = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        parameters = _annotatable_parameters(node)
        annotated_parameters = sum(1 for p in parameters if p.annotation is not None)
        has_return = node.returns is not None

        slots = len(parameters) + 1  # +1 for the return type
        filled = annotated_parameters + (1 if has_return else 0)

        annotated_slots += filled
        total_slots += slots

        if filled == slots:
            fully_typed += 1
        elif filled == 0:
            untyped += 1
        else:
            partially_typed += 1

        owner = owners.get(id(node))
        functions.append({
            "name": f"{owner}.{node.name}" if owner else node.name,
            "lineno": node.lineno,
            "parameters": len(parameters),
            "annotated_parameters": annotated_parameters,
            "has_return_annotation": has_return,
            "coverage": round(filled / slots * 100, 1) if slots else 100.0,
            "is_public": not node.name.startswith("_"),
        })

    annotated_variables = sum(
        1 for node in ast.walk(tree) if isinstance(node, ast.AnnAssign)
    )

    coverage = round(annotated_slots / total_slots * 100, 1) if total_slots else 100.0

    return {
        "file_path": file_path,
        "functions": functions,
        "function_count": len(functions),
        "annotated_slots": annotated_slots,
        "total_slots": total_slots,
        "coverage": coverage,
        "fully_typed": fully_typed,
        "partially_typed": partially_typed,
        "untyped": untyped,
        "annotated_variables": annotated_variables,
        "rating": rate(coverage),
    }


def summarize(file_reports: Sequence[Dict]) -> Dict:
    """
    Aggregate per-file coverage into repository-level statistics.

    Coverage is pooled over *slots*, not averaged over files — otherwise a
    one-function utility module would weigh as much as a thousand-line service.
    """
    annotated_slots = sum(f["annotated_slots"] for f in file_reports)
    total_slots = sum(f["total_slots"] for f in file_reports)
    coverage = round(annotated_slots / total_slots * 100, 1) if total_slots else 0.0

    fully_typed = sum(f["fully_typed"] for f in file_reports)
    partially_typed = sum(f["partially_typed"] for f in file_reports)
    untyped = sum(f["untyped"] for f in file_reports)
    function_count = fully_typed + partially_typed + untyped

    # Worst files first, but only those with enough functions to be meaningful.
    lowest_files = sorted(
        (
            {
                "file_path": f["file_path"],
                "coverage": f["coverage"],
                "function_count": f["function_count"],
                "untyped": f["untyped"],
                "rating": f["rating"],
            }
            for f in file_reports
            if f["function_count"] >= 2
        ),
        key=lambda f: (f["coverage"], -f["function_count"]),
    )[:MAX_LISTED_FILES]

    # Public, entirely unannotated functions are the highest-value fixes: they
    # are the API surface other code type-checks against.
    untyped_public = sorted(
        (
            {
                "file_path": f["file_path"],
                "name": fn["name"],
                "lineno": fn["lineno"],
                "parameters": fn["parameters"],
            }
            for f in file_reports
            for fn in f["functions"]
            if fn["is_public"] and fn["coverage"] == 0.0 and fn["parameters"] > 0
        ),
        key=lambda fn: fn["parameters"],
        reverse=True,
    )[:MAX_LISTED_FUNCTIONS]

    return {
        "coverage": coverage,
        "rating": rate(coverage),
        "annotated_slots": annotated_slots,
        "total_slots": total_slots,
        "function_count": function_count,
        "fully_typed": fully_typed,
        "partially_typed": partially_typed,
        "untyped": untyped,
        "annotated_variables": sum(f["annotated_variables"] for f in file_reports),
        "lowest_files": lowest_files,
        "untyped_public_functions": untyped_public,
    }


def analyze(files: Sequence[Tuple[str, str]]) -> Dict:
    """Run coverage over every file and return the combined report."""
    file_reports = [analyze_file(rel_path, source) for rel_path, source in files]
    # Files with no functions add nothing but noise to the per-file table.
    listed = [f for f in file_reports if f["function_count"] > 0]
    return {"files": listed, **summarize(file_reports)}
