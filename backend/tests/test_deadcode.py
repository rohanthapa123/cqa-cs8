import textwrap

from backend.services import deadcode


def dedent(code: str) -> str:
    return textwrap.dedent(code)


def analyze(*files, total_loc: int = 100):
    """Run the whole-project pass over `(path, source)` pairs."""
    return deadcode.analyze([(path, dedent(src)) for path, src in files], total_loc=total_loc)


# ---------------------------------------------------------------------------
# unreferenced definitions
# ---------------------------------------------------------------------------

def test_finds_function_nobody_calls():
    report = analyze(("app.py", """
        def used():
            return 1

        def _orphan():
            return 2

        print(used())
    """))
    names = {d["name"] for d in report["dead_functions"]}
    assert names == {"_orphan"}


def test_function_called_from_another_file_is_alive():
    report = analyze(
        ("lib.py", "def helper():\n    return 1\n"),
        ("app.py", "from lib import helper\n\nprint(helper())\n"),
    )
    assert report["dead_functions"] == []


def test_recursive_but_uncalled_function_is_still_dead():
    # Self-references are subtracted, so recursion cannot fake reachability.
    report = analyze(("app.py", """
        def _countdown(n):
            if n <= 0:
                return 0
            return _countdown(n - 1)
    """))
    assert {d["name"] for d in report["dead_functions"]} == {"_countdown"}


def test_unreferenced_class_is_reported():
    report = analyze(("models.py", "class _Unused:\n    pass\n"))
    assert {d["name"] for d in report["dead_classes"]} == {"_Unused"}


def test_dunder_and_entrypoint_names_are_never_dead():
    report = analyze(("app.py", """
        class Thing:
            def __init__(self):
                self.x = 1

            def __repr__(self):
                return "Thing()"

        def main():
            return Thing()
    """))
    assert report["dead_functions"] == []


def test_decorated_functions_are_treated_as_reachable():
    report = analyze(("routes.py", """
        from framework import app

        @app.route("/health")
        def health_check():
            return "ok"
    """))
    assert report["dead_functions"] == []


def test_test_functions_are_reachable():
    report = analyze(("tests/test_thing.py", "def test_behaviour():\n    assert True\n"))
    assert report["dead_functions"] == []


def test_subclass_methods_are_not_reported():
    # Reflective dispatch (ast.NodeVisitor.visit -> visit_Name) has no call site.
    report = analyze(("visitor.py", """
        import ast

        class Collector(ast.NodeVisitor):
            def visit_Name(self, node):
                return node
    """))
    assert report["dead_functions"] == []


def test_names_exported_in_dunder_all_are_reachable():
    report = analyze(("api.py", """
        __all__ = ["public_thing"]

        def public_thing():
            return 1
    """))
    assert report["dead_functions"] == []


def test_getattr_string_reference_counts_as_usage():
    report = analyze(
        ("handlers.py", "def handle_ping():\n    return 'pong'\n"),
        ("dispatch.py", "import handlers\n\ngetattr(handlers, 'handle_ping')()\n"),
    )
    assert report["dead_functions"] == []


def test_confidence_is_higher_for_private_definitions():
    report = analyze(("app.py", """
        def _private_orphan():
            return 1

        def public_orphan():
            return 2
    """))
    by_name = {d["name"]: d["confidence"] for d in report["dead_functions"]}
    assert by_name["_private_orphan"] == "high"
    assert by_name["public_orphan"] == "medium"


# ---------------------------------------------------------------------------
# unused imports
# ---------------------------------------------------------------------------

def test_finds_unused_imports():
    report = analyze(("app.py", """
        import os
        import sys
        from typing import Optional

        print(sys.argv)
    """))
    assert {i["name"] for i in report["unused_imports"]} == {"os", "Optional"}


def test_aliased_import_uses_the_bound_name():
    report = analyze(("app.py", "import numpy as np\n\nprint(np.array([1]))\n"))
    assert report["unused_imports"] == []


def test_noqa_suppresses_side_effect_imports():
    report = analyze(("app.py", "from models import Analysis  # noqa: F401 (register table)\n"))
    assert report["unused_imports"] == []


def test_package_init_reexports_are_not_dead():
    report = analyze(("pkg/__init__.py", "from .core import thing\n"))
    assert report["unused_imports"] == []


def test_future_import_is_never_unused():
    report = analyze(("app.py", "from __future__ import annotations\n"))
    assert report["unused_imports"] == []


# ---------------------------------------------------------------------------
# unused locals
# ---------------------------------------------------------------------------

def test_finds_unused_local_variable():
    report = analyze(("app.py", """
        def compute(x):
            unused = x * 2
            result = x + 1
            return result
    """))
    assert {v["name"] for v in report["unused_locals"]} == {"unused"}


def test_variable_read_by_nested_function_is_used():
    report = analyze(("app.py", """
        def outer():
            captured = 1
            def inner():
                return captured
            return inner
    """))
    assert report["unused_locals"] == []


def test_dynamic_scope_access_disables_local_analysis():
    report = analyze(("app.py", """
        def render():
            title = "hello"
            return locals()
    """))
    assert report["unused_locals"] == []


def test_tuple_unpacking_is_not_reported():
    report = analyze(("app.py", """
        def split(pair):
            first, _ = pair
            return 1
    """))
    assert report["unused_locals"] == []


# ---------------------------------------------------------------------------
# unreachable code
# ---------------------------------------------------------------------------

def test_finds_statement_after_return():
    report = analyze(("app.py", """
        def early():
            return 1
            print("never runs")
    """))
    assert len(report["unreachable_code"]) == 1
    assert report["unreachable_code"][0]["after"] == "return"


def test_code_after_conditional_return_is_reachable():
    report = analyze(("app.py", """
        def guard(x):
            if x:
                return 1
            return 2
    """))
    assert report["unreachable_code"] == []


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------

def test_totals_and_percentage():
    report = analyze(
        ("app.py", "import os\n\ndef _orphan():\n    return 1\n"),
        total_loc=50,
    )
    assert report["counts"]["dead_functions"] == 1
    assert report["counts"]["unused_imports"] == 1
    assert report["total_items"] == 2
    assert report["dead_code_percentage"] > 0
    assert report["high_confidence_count"] == 1


def test_syntax_errors_are_skipped_not_fatal():
    report = analyze(("broken.py", "def oops(:\n"), ("fine.py", "def _dead():\n    pass\n"))
    assert {d["name"] for d in report["dead_functions"]} == {"_dead"}
