"""
Dead code detection.

Four kinds of dead weight are reported:

1. **Unreferenced functions and classes** — found by a whole-project
   reachability pass. Every definition in the repository is collected, then
   every *use* of a name anywhere in the repository is counted. A definition
   whose name is never used outside its own body is unreachable.

2. **Unused imports** — a module-level binding that the file never reads.

3. **Unused local variables** — assigned inside a function and never read.

4. **Unreachable statements** — code that follows an unconditional `return`,
   `raise`, `break` or `continue` in the same block.

Python's dynamism makes this necessarily heuristic: `getattr(obj, name)` built
from a runtime string, plugin registries and metaclass magic can all reach code
that looks unreferenced. The analysis is therefore deliberately conservative —
decorated functions, dunder methods, test functions, `__all__` exports and
`__init__.py` re-exports are all treated as reachable — and every finding
carries a confidence level rather than being presented as a certainty.

Self-references do not count: usage occurring *inside* a definition's own body
is subtracted, so a recursive function that nobody calls is still reported.
"""

import ast
import os
from collections import Counter
from typing import Dict, List, Sequence, Set, Tuple

# Names that are always reachable regardless of who references them.
ENTRY_POINT_NAMES = {"main", "app", "application", "handler", "lambda_handler", "cli"}

# Decorators strongly imply the framework calls the function for you.
FRAMEWORK_DECORATOR_HINTS = {
    "route", "get", "post", "put", "patch", "delete", "websocket",
    "task", "job", "command", "group", "fixture", "hookimpl",
    "property", "setter", "getter", "deleter", "cached_property",
    "staticmethod", "classmethod", "abstractmethod", "overload",
    "receiver", "signal", "event", "on", "listens_for", "validator",
    "field_validator", "model_validator", "root_validator",
    "setup", "teardown", "before_request", "after_request",
}

# Imports kept even when unused — they exist for their side effects or typing.
ALWAYS_KEEP_IMPORTS = {"annotations", "*"}

# Reading any of these means we cannot reason about local variable usage.
DYNAMIC_SCOPE_CALLS = {"locals", "vars", "eval", "exec", "globals"}

MAX_ITEMS_PER_CATEGORY = 50


# ---------------------------------------------------------------------------
# usage collection
# ---------------------------------------------------------------------------

class _UsageCollector(ast.NodeVisitor):
    """Counts every name that is *read* — as a variable, or as an attribute."""

    def __init__(self) -> None:
        self.usage: Counter = Counter()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.usage[node.id] += 1
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # `obj.method` reaches `method` without ever naming it as a variable.
        self.usage[node.attr] += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # getattr(obj, "name") is a real, if indirect, reference.
        if isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr", "hasattr", "delattr"):
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                if isinstance(node.args[1].value, str):
                    self.usage[node.args[1].value] += 1
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Everything listed in __all__ is part of the public surface.
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                for element in ast.walk(node.value):
                    if isinstance(element, ast.Constant) and isinstance(element.value, str):
                        self.usage[element.value] += 1
        self.generic_visit(node)


def _count_usage(tree: ast.AST) -> Counter:
    collector = _UsageCollector()
    collector.visit(tree)
    return collector.usage


# ---------------------------------------------------------------------------
# definitions
# ---------------------------------------------------------------------------

def _decorator_names(node: ast.AST) -> List[str]:
    names: List[str] = []
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        while isinstance(target, ast.Attribute):
            names.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            names.append(target.id)
    return names


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _node_lines(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", 0)
    return max(1, end - getattr(node, "lineno", end) + 1)


def _collect_definitions(file_path: str, tree: ast.AST) -> List[Dict]:
    """Every function/class defined in one file, with the context to judge it."""
    definitions: List[Dict] = []
    is_package_init = os.path.basename(file_path) == "__init__.py"

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            decorators = _decorator_names(child)
            kind = "class" if isinstance(child, ast.ClassDef) else "function"
            if isinstance(parent, ast.ClassDef) and kind == "function":
                kind = "method"

            # A method on a subclass may implement a base-class contract or be
            # reached by reflection (`NodeVisitor.visit` dispatching to
            # `visit_Assign`), neither of which appears as a call site.
            inherits = isinstance(parent, ast.ClassDef) and bool([
                base for base in parent.bases
                if not (isinstance(base, ast.Name) and base.id == "object")
            ])

            definitions.append({
                "file_path": file_path,
                "name": child.name,
                "kind": kind,
                "lineno": child.lineno,
                "lines": _node_lines(child),
                "owner": parent.name if isinstance(parent, ast.ClassDef) else None,
                "decorators": decorators,
                "inherits": inherits,
                "is_private": child.name.startswith("_") and not _is_dunder(child.name),
                "is_package_init": is_package_init,
                "self_usage": _count_usage(child),
            })

    return definitions


def _is_reachable_by_convention(definition: Dict, file_path: str) -> bool:
    """Definitions we refuse to call dead, however unreferenced they look."""
    name = definition["name"]

    if _is_dunder(name):
        return True
    if name in ENTRY_POINT_NAMES:
        return True
    if name.startswith("test_") or name.startswith("Test"):
        return True
    if definition["is_package_init"]:
        return True  # __init__.py exists to re-export
    if any(d in FRAMEWORK_DECORATOR_HINTS for d in definition["decorators"]):
        return True
    # Any decorator at all on a method usually means a framework owns the call.
    if definition["decorators"] and definition["kind"] == "method":
        return True
    if definition["kind"] == "method" and definition["inherits"]:
        return True  # may override a base method, or be dispatched reflectively

    base = os.path.basename(file_path)
    if base in ("conftest.py", "setup.py", "manage.py", "wsgi.py", "asgi.py"):
        return True

    return False


def _confidence(definition: Dict) -> str:
    """
    How sure we are that this really is dead.

    Private, undecorated module-level functions are the safe case. Public
    methods are the risky one — they may be an interface implementation that
    is only ever called through a base class reference.
    """
    if definition["decorators"]:
        return "low"
    if definition["kind"] == "method" and not definition["is_private"]:
        return "low"
    if definition["is_private"]:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# unused imports
# ---------------------------------------------------------------------------

def find_unused_imports(tree: ast.AST, file_usage: Counter, file_path: str,
                        source: str = "") -> List[Dict]:
    """
    Module-level import bindings the file never reads.

    An import marked `# noqa` is intentional — it is usually there to register
    a model, install a plugin or re-export a name — so it is left alone.
    """
    if os.path.basename(file_path) == "__init__.py":
        return []  # re-export surface, not dead code

    lines = source.splitlines()

    def suppressed(lineno: int) -> bool:
        if 0 < lineno <= len(lines):
            return "# noqa" in lines[lineno - 1].lower()
        return False

    unused: List[Dict] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if suppressed(node.lineno):
                continue
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound in ALWAYS_KEEP_IMPORTS:
                    continue
                if file_usage.get(bound, 0) == 0:
                    unused.append({
                        "file_path": file_path,
                        "lineno": node.lineno,
                        "name": bound,
                        "statement": f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                    })

        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__" or suppressed(node.lineno):
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                if file_usage.get(bound, 0) == 0:
                    unused.append({
                        "file_path": file_path,
                        "lineno": node.lineno,
                        "name": bound,
                        "statement": f"from {node.module or '.'} import {alias.name}"
                                     + (f" as {alias.asname}" if alias.asname else ""),
                    })

    return unused


# ---------------------------------------------------------------------------
# unused local variables
# ---------------------------------------------------------------------------

def _assigned_locals(func: ast.AST) -> List[Tuple[str, int]]:
    """
    Plain `name = ...` bindings in a function body.

    Tuple unpacking is skipped on purpose: `a, _ = pair()` is the idiomatic way
    to discard a value, and flagging it produces nothing but noise.
    """
    assigned: List[Tuple[str, int]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                assigned.append((target.id, node.lineno))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            assigned.append((node.target.id, node.lineno))
    return assigned


def find_unused_locals(func: ast.AST, file_path: str) -> List[Dict]:
    declared_elsewhere: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            declared_elsewhere.update(node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in DYNAMIC_SCOPE_CALLS:
                return []  # the scope can be read dynamically; no conclusions

    usage = _count_usage(func)
    parameters = set()
    args = getattr(func, "args", None)
    if args is not None:
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            parameters.add(arg.arg)
        for arg in (args.vararg, args.kwarg):
            if arg is not None:
                parameters.add(arg.arg)

    unused: List[Dict] = []
    seen: Set[str] = set()
    for name, lineno in _assigned_locals(func):
        if name in seen or name in parameters or name in declared_elsewhere:
            continue
        if name == "_" or name.startswith("__"):
            continue
        if usage.get(name, 0) == 0:
            seen.add(name)
            unused.append({
                "file_path": file_path,
                "function": func.name,
                "name": name,
                "lineno": lineno,
            })

    return unused


# ---------------------------------------------------------------------------
# unreachable statements
# ---------------------------------------------------------------------------

_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def find_unreachable(tree: ast.AST, file_path: str) -> List[Dict]:
    """Statements that follow an unconditional exit in the same block."""
    unreachable: List[Dict] = []

    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for index, statement in enumerate(block[:-1]):
                if isinstance(statement, _TERMINATORS):
                    following = block[index + 1]
                    unreachable.append({
                        "file_path": file_path,
                        "lineno": following.lineno,
                        "after": type(statement).__name__.lower(),
                        "after_line": statement.lineno,
                        "statements": len(block) - index - 1,
                    })
                    break

    return unreachable


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def analyze(files: Sequence[Tuple[str, str]], total_loc: int = 0) -> Dict:
    """
    Whole-project dead code pass.

    Two sweeps: the first parses every file and accumulates a repository-wide
    usage count, the second decides which definitions that count never reaches.
    """
    trees: List[Tuple[str, ast.AST, str]] = []
    for rel_path, source in files:
        try:
            trees.append((rel_path, ast.parse(source), source))
        except SyntaxError:
            continue

    project_usage: Counter = Counter()
    definitions: List[Dict] = []
    unused_imports: List[Dict] = []
    unused_locals: List[Dict] = []
    unreachable: List[Dict] = []

    for rel_path, tree, source in trees:
        file_usage = _count_usage(tree)
        project_usage.update(file_usage)
        definitions.extend(_collect_definitions(rel_path, tree))
        unused_imports.extend(find_unused_imports(tree, file_usage, rel_path, source))
        unreachable.extend(find_unreachable(tree, rel_path))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                unused_locals.extend(find_unused_locals(node, rel_path))

    dead_functions: List[Dict] = []
    dead_classes: List[Dict] = []

    for definition in definitions:
        name = definition["name"]
        if _is_reachable_by_convention(definition, definition["file_path"]):
            continue

        # Subtract self-references so recursive-but-uncalled code still counts.
        external_uses = project_usage.get(name, 0) - definition["self_usage"].get(name, 0)
        if external_uses > 0:
            continue

        entry = {
            "file_path": definition["file_path"],
            "name": name,
            "kind": definition["kind"],
            "lineno": definition["lineno"],
            "lines": definition["lines"],
            "owner": definition["owner"],
            "confidence": _confidence(definition),
        }
        (dead_classes if definition["kind"] == "class" else dead_functions).append(entry)

    dead_functions.sort(key=lambda d: d["lines"], reverse=True)
    dead_classes.sort(key=lambda d: d["lines"], reverse=True)
    unused_imports.sort(key=lambda d: (d["file_path"], d["lineno"]))
    unused_locals.sort(key=lambda d: (d["file_path"], d["lineno"]))
    unreachable.sort(key=lambda d: (d["file_path"], d["lineno"]))

    dead_lines = sum(d["lines"] for d in dead_functions) + sum(d["lines"] for d in dead_classes)
    total_items = (
        len(dead_functions) + len(dead_classes)
        + len(unused_imports) + len(unused_locals) + len(unreachable)
    )

    return {
        "dead_functions": dead_functions[:MAX_ITEMS_PER_CATEGORY],
        "dead_classes": dead_classes[:MAX_ITEMS_PER_CATEGORY],
        "unused_imports": unused_imports[:MAX_ITEMS_PER_CATEGORY],
        "unused_locals": unused_locals[:MAX_ITEMS_PER_CATEGORY],
        "unreachable_code": unreachable[:MAX_ITEMS_PER_CATEGORY],
        "counts": {
            "dead_functions": len(dead_functions),
            "dead_classes": len(dead_classes),
            "unused_imports": len(unused_imports),
            "unused_locals": len(unused_locals),
            "unreachable_code": len(unreachable),
        },
        "total_items": total_items,
        "dead_lines": dead_lines,
        "dead_code_percentage": round(dead_lines / total_loc * 100, 2) if total_loc else 0.0,
        "high_confidence_count": sum(
            1 for d in [*dead_functions, *dead_classes] if d["confidence"] == "high"
        ),
    }
