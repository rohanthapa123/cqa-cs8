import textwrap

from backend.services import complexity, duplication, maintainability, practices
from backend.services.analysis import (
    compute_health_score,
    file_stats,
    is_python_project,
    collect_python_files,
)


def dedent(code: str) -> str:
    return textwrap.dedent(code)


# ---------------------------------------------------------------------------
# 1. Cyclomatic complexity
# ---------------------------------------------------------------------------

def test_complexity_simple_function():
    report = complexity.analyze_file("f.py", dedent("""
        def foo():
            return 1
    """))
    names = {fn["name"]: fn for fn in report["functions"]}
    assert "foo" in names
    assert names["foo"]["complexity"] >= 1
    assert names["foo"]["is_high_risk"] is False


def test_complexity_branchy_function():
    report = complexity.analyze_file("f.py", dedent("""
        def bar(x):
            if x > 0:
                if x > 10:
                    return "high"
                return "mid"
            return "low"
    """))
    bar = next(fn for fn in report["functions"] if fn["name"] == "bar")
    assert bar["complexity"] >= 3


def test_complexity_empty_file():
    report = complexity.analyze_file("f.py", "")
    assert report["functions"] == []
    assert report["average_complexity"] == 0.0


def test_complexity_summarize_high_risk():
    # a function with many branches to exceed the CC>10 threshold
    body = "\n".join(f"    if x == {i}: return {i}" for i in range(15))
    report = complexity.analyze_file("big.py", f"def big(x):\n{body}\n")
    summary = complexity.summarize([report])
    assert summary["function_count"] == 1
    assert len(summary["high_risk_functions"]) == 1
    assert summary["high_risk_functions"][0]["file_path"] == "big.py"
    assert summary["distribution"]["high"] == 1


# ---------------------------------------------------------------------------
# 2. Duplicate detection (Winnowing)
# ---------------------------------------------------------------------------

def test_winnowing_identical_files_are_duplicates():
    src = dedent("""
        def process(values):
            total = 0
            for value in values:
                if value > 0:
                    total = total + value
            return total
    """)
    report = duplication.analyze(
        [("a.py", src), ("b.py", src)],
        loc_by_file={"a.py": 6, "b.py": 6},
    )
    assert report["pair_count"] == 1
    pair = report["duplicate_pairs"][0]
    assert pair["similarity"] == 100.0
    assert pair["blocks_a"]  # non-empty line ranges
    # each block carries its actual source code + line range
    block = pair["blocks_a"][0]
    assert {"start", "end", "code"} <= block.keys()
    assert block["code"].strip()
    assert report["duplication_percentage"] > 0


def test_winnowing_matches_after_renaming():
    a = dedent("""
        def process(values):
            total = 0
            for value in values:
                total = total + value
            return total
    """)
    b = dedent("""
        def handle(items):
            acc = 0
            for item in items:
                acc = acc + item
            return acc
    """)
    report = duplication.analyze([("a.py", a), ("b.py", b)], {"a.py": 5, "b.py": 5})
    # AST normalization makes the renamed copy match strongly
    assert report["pair_count"] == 1
    assert report["duplicate_pairs"][0]["similarity"] >= 90.0


def test_winnowing_distinct_files_not_duplicates():
    a = "def add(x, y):\n    return x + y\n"
    b = dedent("""
        class Config:
            def __init__(self):
                self.debug = False
            def toggle(self):
                self.debug = not self.debug
    """)
    report = duplication.analyze([("a.py", a), ("b.py", b)], {"a.py": 2, "b.py": 5})
    assert report["pair_count"] == 0
    assert report["duplication_percentage"] == 0.0


# ---------------------------------------------------------------------------
# 3. Halstead + Maintainability Index
# ---------------------------------------------------------------------------

def test_maintainability_halstead_metrics_present():
    report = maintainability.analyze_file("f.py", dedent("""
        def calc(a, b):
            result = a * b + a - b
            return result
    """), cc_total=1, loc=3)
    h = report["halstead"]
    assert h["vocabulary"] == h["distinct_operators"] + h["distinct_operands"]
    assert h["length"] == h["total_operators"] + h["total_operands"]
    assert h["volume"] > 0
    assert h["difficulty"] > 0
    assert h["effort"] > 0


def test_maintainability_index_range_and_rating():
    report = maintainability.analyze_file("f.py", "def f():\n    return 1\n", cc_total=1, loc=2)
    mi = report["maintainability_index"]
    assert 0 <= mi <= 100
    assert report["rating"] in {"Excellent", "Good", "Fair", "Poor"}
    # a trivial function should be highly maintainable
    assert report["rating"] == "Excellent"


def test_maintainability_summarize():
    reports = [
        maintainability.analyze_file("a.py", "def a():\n    return 1\n", 1, 2),
        maintainability.analyze_file("b.py", "def b():\n    return 2\n", 1, 2),
    ]
    summary = maintainability.summarize(reports)
    assert 0 <= summary["average_maintainability"] <= 100
    assert len(summary["lowest_files"]) == 2


# ---------------------------------------------------------------------------
# Auxiliary: bad practices
# ---------------------------------------------------------------------------

def test_bad_practice_bare_except():
    issues = practices.detect(dedent("""
        try:
            pass
        except:
            pass
    """))
    assert any(i["type"] == "bare_except" for i in issues)


def test_bad_practice_wildcard_import():
    issues = practices.detect("from os import *\n")
    assert any(i["type"] == "wildcard_import" for i in issues)


def test_bad_practice_eval():
    issues = practices.detect("eval('1+1')\n")
    assert any(i["type"] == "dangerous_call" for i in issues)


def test_bad_practice_mutable_default():
    issues = practices.detect(dedent("""
        def foo(items=[]):
            pass
    """))
    assert any(i["type"] == "mutable_default_arg" for i in issues)


def test_bad_practice_too_many_args():
    issues = practices.detect(dedent("""
        def foo(a, b, c, d, e, f):
            pass
    """))
    assert any(i["type"] == "too_many_args" for i in issues)


def test_no_bad_practices_clean_code():
    issues = practices.detect(dedent("""
        def add(a, b):
            return a + b
    """))
    assert issues == []


# ---------------------------------------------------------------------------
# Project detection + stats + health score
# ---------------------------------------------------------------------------

def test_is_python_project(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    assert is_python_project(str(tmp_path)) is True


def test_is_not_python_project(tmp_path):
    (tmp_path / "index.js").write_text("console.log('hi')")
    assert is_python_project(str(tmp_path)) is False


def test_collect_python_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.js").write_text("")
    files = collect_python_files(str(tmp_path))
    assert len(files) == 2
    assert all(f.endswith(".py") for f in files)


def test_file_stats_counts():
    stats = file_stats(dedent("""
        # a comment
        class A:
            def method(self):
                return 1

        def top():
            pass
    """))
    assert stats["classes"] == 1
    assert stats["functions"] == 2
    assert stats["loc"] > 0  # blank + comment lines excluded


def test_health_score_good_repo():
    health = compute_health_score(avg_maintainability=90, avg_complexity=3, duplication_percentage=0)
    assert health["score"] >= 80
    assert health["grade"] == "A"
    assert set(health["components"]) == {"maintainability", "complexity", "duplication"}


def test_health_score_poor_repo():
    health = compute_health_score(avg_maintainability=20, avg_complexity=30, duplication_percentage=80)
    assert health["score"] < 50
    assert health["grade"] in {"D", "F"}
