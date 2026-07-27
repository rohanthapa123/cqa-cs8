"""
Bad-practices detection (secondary utility panel).

A lightweight AST linter that flags a handful of common Python smells. This is
an auxiliary panel, not one of the three core analysis modules.
"""

import ast
from typing import Dict, List

MAX_ARGS = 5


def detect(source: str) -> List[Dict]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    issues: List[Dict] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({"line": node.lineno, "type": "bare_except",
                           "message": "Bare except clause catches all exceptions"})

        elif isinstance(node, ast.Global):
            for name in node.names:
                issues.append({"line": node.lineno, "type": "global_variable",
                               "message": f"Global variable usage: '{name}'"})

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append({"line": node.lineno, "type": "mutable_default_arg",
                                   "message": f"Mutable default argument in '{node.name}'"})
            num_args = len(node.args.args)
            if num_args > MAX_ARGS:
                issues.append({"line": node.lineno, "type": "too_many_args",
                               "message": f"'{node.name}' has {num_args} arguments (>{MAX_ARGS})"})

        elif isinstance(node, ast.ImportFrom) and node.names:
            for alias in node.names:
                if alias.name == "*":
                    issues.append({"line": node.lineno, "type": "wildcard_import",
                                   "message": f"Wildcard import from '{node.module}'"})

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                issues.append({"line": node.lineno, "type": "dangerous_call",
                               "message": f"Use of '{node.func.id}()' is a security risk"})

    return issues
