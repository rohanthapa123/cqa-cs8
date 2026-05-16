import ast
import os
import shutil
import tempfile
from typing import List, Dict, Tuple

from git import Repo
from radon.complexity import cc_visit
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PYTHON_INDICATORS = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"}


# ---------------------------------------------------------------------------
# repo helpers
# ---------------------------------------------------------------------------

def clone_repo(github_url: str) -> str:
    temp_dir = tempfile.mkdtemp(prefix="repo_clone_")
    try:
        Repo.clone_from(github_url, temp_dir, depth=1)
    except Exception as e:
        shutil.rmtree(temp_dir)
        raise RuntimeError(f"Failed to clone repository: {e}")
    return temp_dir


def is_python_project(root_dir: str) -> bool:
    for dirpath, _, filenames in os.walk(root_dir):
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


# ---------------------------------------------------------------------------
# cyclomatic complexity (radon)
# ---------------------------------------------------------------------------

def compute_cyclomatic_complexity(file_path: str) -> Dict[str, Dict[str, int]]:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    try:
        analysis = cc_visit(source)
    except Exception:
        analysis = []
    return {block.name: {"complexity": block.complexity, "lineno": block.lineno} for block in analysis}


# ---------------------------------------------------------------------------
# duplicate detection (TF-IDF + cosine similarity)
# ---------------------------------------------------------------------------

def compute_tfidf_cosine_similarity(
    file_paths: List[str],
) -> Tuple[Dict[str, List[float]], List[Tuple[str, str, float]]]:
    documents = []
    for fp in file_paths:
        with open(fp, "r", encoding="utf-8") as f:
            documents.append(f.read())
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(documents)
    tfidf_vectors = {fp: tfidf_matrix[idx].toarray().flatten().tolist() for idx, fp in enumerate(file_paths)}
    sim_matrix = cosine_similarity(tfidf_matrix)
    n = len(file_paths)
    pairs = [
        (file_paths[i], file_paths[j], sim_matrix[i, j])
        for i in range(n)
        for j in range(i + 1, n)
    ]
    top_pairs = sorted(pairs, key=lambda x: x[2], reverse=True)[:5]
    return tfidf_vectors, top_pairs


# ---------------------------------------------------------------------------
# time complexity (AST loop-depth → Big-O)
# ---------------------------------------------------------------------------

def _max_loop_depth(node: ast.AST, depth: int = 0) -> int:
    max_d = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While)):
            d = _max_loop_depth(child, depth + 1)
        else:
            d = _max_loop_depth(child, depth)
        if d > max_d:
            max_d = d
    return max_d


def _is_recursive(func_node: ast.FunctionDef) -> bool:
    for node in ast.walk(func_node):
        if node is func_node:
            continue
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == func_node.name:
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr == func_node.name:
                return True
    return False


def _depth_to_bigo(depth: int, recursive: bool) -> str:
    if recursive:
        return "O(2^n)"
    if depth == 0:
        return "O(1)"
    if depth == 1:
        return "O(n)"
    if depth == 2:
        return "O(n^2)"
    if depth == 3:
        return "O(n^3)"
    return f"O(n^{depth})"


def compute_time_complexity(file_path: str) -> Dict[str, Dict]:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    results = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            depth = _max_loop_depth(node)
            recursive = _is_recursive(node)
            results[node.name] = {
                "complexity": _depth_to_bigo(depth, recursive),
                "lineno": node.lineno,
                "is_recursive": recursive,
            }
    return results


# ---------------------------------------------------------------------------
# bad practices (AST)
# ---------------------------------------------------------------------------

def detect_bad_practices(file_path: str) -> List[Dict]:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    issues = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({"line": node.lineno, "type": "bare_except", "message": "Bare except clause catches all exceptions"})

        elif isinstance(node, ast.Global):
            for name in node.names:
                issues.append({"line": node.lineno, "type": "global_variable", "message": f"Global variable usage: '{name}'"})

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append({"line": node.lineno, "type": "mutable_default_arg", "message": f"Mutable default argument in '{node.name}'"})
            num_args = len(node.args.args)
            if num_args > 5:
                issues.append({"line": node.lineno, "type": "too_many_args", "message": f"'{node.name}' has {num_args} arguments (>5)"})

        elif isinstance(node, ast.ImportFrom) and node.names:
            for alias in node.names:
                if alias.name == "*":
                    issues.append({"line": node.lineno, "type": "wildcard_import", "message": f"Wildcard import from '{node.module}'"})

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                issues.append({"line": node.lineno, "type": "dangerous_call", "message": f"Use of '{node.func.id}()' is a security risk"})

    return issues


# ---------------------------------------------------------------------------
# test detection
# ---------------------------------------------------------------------------

def detect_tests(root_dir: str, py_files: List[str]) -> Dict:
    """
    Identifies test files by name convention (test_*.py / *_test.py)
    and by presence of a tests/ or test/ directory.
    """
    test_files = [
        fp for fp in py_files
        if os.path.basename(fp).startswith("test_") or os.path.basename(fp).endswith("_test.py")
    ]
    return {
        "has_tests": len(test_files) > 0,
        "test_files": test_files,
        "test_count": len(test_files),
    }


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

def analyze_repository(github_url: str) -> Dict:
    repo_path = clone_repo(github_url)
    try:
        if not is_python_project(repo_path):
            raise ValueError("Not a Python project: no .py files or Python project files found")

        py_files = collect_python_files(repo_path)

        complexity_report = {fp: compute_cyclomatic_complexity(fp) for fp in py_files}
        _, top_pairs = compute_tfidf_cosine_similarity(py_files)
        similarity_dict = {f"{a}||{b}": sim for a, b, sim in top_pairs}
        time_complexity_report = {fp: compute_time_complexity(fp) for fp in py_files}
        bad_practices_report = {fp: detect_bad_practices(fp) for fp in py_files}
        test_coverage = detect_tests(repo_path, py_files)

        return {
            "cyclomatic_complexity": complexity_report,
            "similarity_matrix": similarity_dict,
            "time_complexity": time_complexity_report,
            "bad_practices": bad_practices_report,
            "test_coverage": test_coverage,
        }
    finally:
        shutil.rmtree(repo_path, ignore_errors=True)
