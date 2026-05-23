import textwrap
import pytest
from backend.services.analysis import (
    compute_cyclomatic_complexity,
    compute_time_complexity,
    detect_bad_practices,
    detect_tests,
    is_python_project,
    collect_python_files,
)
import tempfile, os


def write_tmp(code: str, suffix=".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(textwrap.dedent(code))
    f.close()
    return f.name


# --- cyclomatic complexity ---

def test_cyclomatic_simple_function():
    path = write_tmp("""
        def foo():
            return 1
    """)
    result = compute_cyclomatic_complexity(path)
    os.unlink(path)
    assert "foo" in result
    assert result["foo"]["complexity"] >= 1


def test_cyclomatic_branchy_function():
    path = write_tmp("""
        def bar(x):
            if x > 0:
                if x > 10:
                    return "high"
                return "mid"
            return "low"
    """)
    result = compute_cyclomatic_complexity(path)
    os.unlink(path)
    assert result["bar"]["complexity"] >= 3


def test_cyclomatic_empty_file():
    path = write_tmp("")
    result = compute_cyclomatic_complexity(path)
    os.unlink(path)
    assert result == {}


# --- time complexity ---

def test_time_complexity_constant():
    path = write_tmp("""
        def constant():
            return 42
    """)
    result = compute_time_complexity(path)
    os.unlink(path)
    assert result["constant"]["complexity"] == "O(1)"


def test_time_complexity_linear():
    path = write_tmp("""
        def linear(items):
            for item in items:
                print(item)
    """)
    result = compute_time_complexity(path)
    os.unlink(path)
    assert result["linear"]["complexity"] == "O(n)"


def test_time_complexity_quadratic():
    path = write_tmp("""
        def quadratic(matrix):
            for row in matrix:
                for col in row:
                    print(col)
    """)
    result = compute_time_complexity(path)
    os.unlink(path)
    assert result["quadratic"]["complexity"] == "O(n^2)"


def test_time_complexity_recursive():
    path = write_tmp("""
        def fib(n):
            if n <= 1:
                return n
            return fib(n-1) + fib(n-2)
    """)
    result = compute_time_complexity(path)
    os.unlink(path)
    assert result["fib"]["is_recursive"] is True
    assert result["fib"]["complexity"] == "O(2^n)"


# --- bad practices ---

def test_bad_practice_bare_except():
    path = write_tmp("""
        try:
            pass
        except:
            pass
    """)
    issues = detect_bad_practices(path)
    os.unlink(path)
    types = [i["type"] for i in issues]
    assert "bare_except" in types


def test_bad_practice_wildcard_import():
    path = write_tmp("from os import *\n")
    issues = detect_bad_practices(path)
    os.unlink(path)
    assert any(i["type"] == "wildcard_import" for i in issues)


def test_bad_practice_eval():
    path = write_tmp("eval('1+1')\n")
    issues = detect_bad_practices(path)
    os.unlink(path)
    assert any(i["type"] == "dangerous_call" for i in issues)


def test_bad_practice_mutable_default():
    path = write_tmp("""
        def foo(items=[]):
            pass
    """)
    issues = detect_bad_practices(path)
    os.unlink(path)
    assert any(i["type"] == "mutable_default_arg" for i in issues)


def test_bad_practice_too_many_args():
    path = write_tmp("""
        def foo(a, b, c, d, e, f):
            pass
    """)
    issues = detect_bad_practices(path)
    os.unlink(path)
    assert any(i["type"] == "too_many_args" for i in issues)


def test_no_bad_practices_clean_code():
    path = write_tmp("""
        def add(a, b):
            return a + b
    """)
    issues = detect_bad_practices(path)
    os.unlink(path)
    assert issues == []


# --- project detection ---

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


# --- test detection ---

def test_detect_tests_found(tmp_path):
    py_files = [str(tmp_path / "test_auth.py"), str(tmp_path / "main.py")]
    for f in py_files:
        open(f, "w").close()
    result = detect_tests(str(tmp_path), py_files)
    assert result["has_tests"] is True
    assert result["test_count"] == 1
    assert any("test_auth.py" in f for f in result["test_files"])


def test_detect_tests_suffix_convention(tmp_path):
    py_files = [str(tmp_path / "auth_test.py"), str(tmp_path / "utils.py")]
    for f in py_files:
        open(f, "w").close()
    result = detect_tests(str(tmp_path), py_files)
    assert result["has_tests"] is True
    assert result["test_count"] == 1


def test_detect_tests_none(tmp_path):
    py_files = [str(tmp_path / "main.py"), str(tmp_path / "utils.py")]
    for f in py_files:
        open(f, "w").close()
    result = detect_tests(str(tmp_path), py_files)
    assert result["has_tests"] is False
    assert result["test_count"] == 0
    assert result["test_files"] == []
