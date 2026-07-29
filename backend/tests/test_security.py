import textwrap

from backend.services import security


def dedent(code: str) -> str:
    return textwrap.dedent(code)


def rules(source: str):
    """Rule names raised by the AST vulnerability pass for one snippet."""
    return {issue["rule"] for issue in security.detect_code_issues(dedent(source))}


# ---------------------------------------------------------------------------
# vulnerability patterns
# ---------------------------------------------------------------------------

def test_detects_eval_and_exec():
    assert "dangerous_eval" in rules("""
        def run(payload):
            return eval(payload)
    """)


def test_detects_shell_injection_vectors():
    assert "shell_command" in rules("""
        import os
        os.system("rm -rf " + path)
    """)
    assert "subprocess_shell" in rules("""
        import subprocess
        subprocess.run(f"cat {name}", shell=True)
    """)


def test_subprocess_without_shell_is_clean():
    assert "subprocess_shell" not in rules("""
        import subprocess
        subprocess.run(["cat", name])
    """)


def test_detects_unsafe_deserialization():
    assert "unsafe_deserialization" in rules("""
        import pickle
        data = pickle.loads(blob)
    """)


def test_detects_unsafe_yaml_but_allows_safe_loader():
    assert "unsafe_yaml" in rules("""
        import yaml
        yaml.load(stream)
    """)
    assert "unsafe_yaml" not in rules("""
        import yaml
        yaml.load(stream, Loader=yaml.SafeLoader)
    """)
    assert "unsafe_yaml" not in rules("""
        import yaml
        yaml.safe_load(stream)
    """)


def test_detects_disabled_tls_verification():
    assert "tls_verification_disabled" in rules("""
        import requests
        requests.get(url, verify=False)
    """)


def test_detects_weak_hash_unless_marked_non_security():
    assert "weak_hash" in rules("""
        import hashlib
        hashlib.md5(data).hexdigest()
    """)
    # The explicit opt-out means "this is a fingerprint, not a security control".
    assert "weak_hash" not in rules("""
        import hashlib
        hashlib.md5(data, usedforsecurity=False).hexdigest()
    """)


def test_detects_sql_string_interpolation():
    assert "sql_injection" in rules("""
        cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    """)
    assert "sql_injection" in rules("""
        cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)
    """)


def test_parameterised_sql_is_clean():
    assert "sql_injection" not in rules("""
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    """)


def test_comments_and_docstrings_are_not_scanned():
    # The whole point of walking the AST rather than the raw text.
    assert rules('''
        def safe():
            """Never call eval(user_input) here."""
            # os.system("rm -rf /")
            return 1
    ''') == set()


def test_syntax_error_does_not_raise():
    assert security.detect_code_issues("def broken(:\n") == []


# ---------------------------------------------------------------------------
# hardcoded secrets
# ---------------------------------------------------------------------------

def secret_rules(source: str):
    return {finding["rule"] for finding in security.detect_secrets(dedent(source))}


def test_detects_secret_shaped_assignment():
    assert "hardcoded_secret" in secret_rules("""
        DATABASE_PASSWORD = "hunter2-real-production-value"
    """)


def test_ignores_placeholder_values():
    assert secret_rules("""
        JWT_SECRET = "change-me-in-production"
        API_KEY = "your_api_key_here"
    """) == set()


def test_ignores_urls_named_like_credentials():
    # Regression: GITHUB_TOKEN_URL is a URL, not a token.
    assert secret_rules("""
        GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
    """) == set()


def test_detects_known_token_formats():
    assert "exposed_aws_access_key" in secret_rules("""
        value = "AKIAIOSFODNN7EXAMPLE"
    """)
    assert "exposed_private_key" in secret_rules('''
        KEY = """-----BEGIN RSA PRIVATE KEY-----"""
    ''')


def test_secret_values_are_redacted():
    findings = security.detect_secrets(dedent("""
        SECRET_TOKEN = "abcd1234efgh5678ijkl"
    """))
    assert findings
    assert "abcd1234efgh5678ijkl" not in findings[0]["match"]
    assert findings[0]["match"].startswith("abcd")


def test_high_entropy_string_is_flagged():
    assert "high_entropy_string" in secret_rules("""
        blob = "xQ7pL2vR9wZ4mK8nT5jH3bF6cY1dS0gA"
    """)


def test_low_entropy_string_is_not_flagged():
    assert "high_entropy_string" not in secret_rules("""
        message = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    """)


def test_shannon_entropy_ordering():
    assert security.shannon_entropy("") == 0.0
    assert security.shannon_entropy("aaaaaaaa") == 0.0
    assert security.shannon_entropy("xQ7pL2vR9wZ4mK8n") > 3.5


# ---------------------------------------------------------------------------
# scoring + orchestration
# ---------------------------------------------------------------------------

def test_clean_repository_scores_100():
    assert security.compute_security_score({"critical": 0, "high": 0, "medium": 0, "low": 0}) == 100.0


def test_score_decays_and_never_reaches_zero():
    few = security.compute_security_score({"critical": 1}, total_loc=1000)
    many = security.compute_security_score({"critical": 10}, total_loc=1000)
    assert 0.0 < many < few < 100.0


def test_code_findings_are_scored_by_density_not_count():
    # The same defect rate must score the same at any codebase size.
    small = security.compute_security_score({"high": 1}, total_loc=1000)
    large = security.compute_security_score({"high": 10}, total_loc=10_000)
    assert small == large


def test_a_denser_codebase_scores_worse():
    sparse = security.compute_security_score({"high": 1}, total_loc=10_000)
    dense = security.compute_security_score({"high": 1}, total_loc=500)
    assert dense < sparse


def test_dependency_advisories_are_scored_absolutely():
    # A vulnerable package is equally exploitable whatever the project's size,
    # so its penalty must not be diluted by a large codebase.
    small = security.compute_security_score({}, {"critical": 1}, total_loc=1000)
    large = security.compute_security_score({}, {"critical": 1}, total_loc=100_000)
    assert small == large < 100.0


def test_multiple_advisories_against_one_package_are_charged_once(monkeypatch):
    # Eight CVEs in one dependency still need exactly one version bump.
    monkeypatch.setattr(security, "scan_dependencies", lambda root: {
        "available": True, "reason": None, "dependencies_checked": 1, "unpinned_count": 0,
        "vulnerable_package_count": 1,
        "vulnerabilities": [
            {"package": "leaky", "version": "1.0", "pinned": True, "constraint": "==1.0",
             "source": "requirements.txt", "vulnerability_id": f"GHSA-{i}", "cve": None,
             "severity": sev, "summary": "", "fixed_versions": ["2.0"], "reference": ""}
            for i, sev in enumerate(["high", "high", "medium", "low"])
        ],
    })

    report = security.analyze([("app.py", "x = 1\n")], root_dir="/tmp", total_loc=1000)

    # All four advisories are reported...
    assert report["total_issues"] == 4
    # ...but scored as the single worst severity for that one package.
    assert report["security_score"] == security.compute_security_score({}, {"high": 1}, 1000)


def test_analyze_groups_by_file_and_skips_dependency_scan():
    report = security.analyze(
        [
            ("app.py", "import os\nos.system(cmd)\n"),
            ("clean.py", "def add(a, b):\n    return a + b\n"),
        ],
        root_dir=None,
        scan_deps=False,
    )
    assert report["affected_files"] == 1
    assert report["files"][0]["file_path"] == "app.py"
    assert report["severity_counts"]["high"] >= 1
    assert report["dependencies"]["available"] is False


def test_assert_flagged_in_source_but_not_in_tests():
    source = "def check(x):\n    assert x > 0\n"
    production = security.analyze([("app.py", source)], scan_deps=False)
    tests = security.analyze([("tests/test_app.py", source)], scan_deps=False)
    assert production["total_issues"] == 1
    assert tests["total_issues"] == 0


def test_findings_in_test_code_are_downgraded_and_labelled():
    # `pickle.loads` in a test suite is usually exercising the behaviour, not
    # shipping it — high in production, medium in tests.
    source = "import pickle\npickle.loads(blob)\n"
    production = security.analyze([("app.py", source)], scan_deps=False)
    tests = security.analyze([("tests/test_app.py", source)], scan_deps=False)

    assert production["files"][0]["issues"][0]["severity"] == "high"
    assert production["files"][0]["issues"][0]["in_test"] is False
    assert tests["files"][0]["issues"][0]["severity"] == "medium"
    assert tests["files"][0]["issues"][0]["in_test"] is True
    assert tests["test_issues"] == 1
    assert tests["security_score"] > production["security_score"]


def test_low_severity_cannot_be_downgraded_below_low():
    assert security._downgrade("low") == "low"
    assert security._downgrade("critical") == "high"


def test_production_files_are_listed_before_test_files():
    source = "import pickle\npickle.loads(blob)\n"
    report = security.analyze(
        [("tests/test_app.py", source), ("app.py", source)], scan_deps=False
    )
    assert [f["file_path"] for f in report["files"]] == ["app.py", "tests/test_app.py"]


def test_test_directory_variants_are_recognised():
    assert security._is_test_file("tests/test_x.py")
    assert security._is_test_file("test/helpers.py")
    assert security._is_test_file("pkg/x_test.py")
    assert security._is_test_file("conftest.py")
    assert not security._is_test_file("app/latest.py")


# ---------------------------------------------------------------------------
# dependency parsing
# ---------------------------------------------------------------------------

def test_parses_pinned_and_unpinned_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "# a comment\n"
        "fastapi==0.111.0\n"
        "requests[security]>=2.31.0\n"
        "urllib3~=2.0.1\n"
        "unpinned-package\n"
        "conditional==1.0.0 ; python_version < '3.9'\n"
    )
    parsed = {d["name"]: d for d in security.parse_requirements(str(tmp_path))}

    assert parsed["fastapi"]["version"] == "0.111.0"
    assert parsed["fastapi"]["pinned"] is True
    assert parsed["requests"]["version"] == "2.31.0"
    assert parsed["requests"]["pinned"] is False
    assert parsed["urllib3"]["pinned"] is False
    assert "unpinned-package" not in parsed
    assert parsed["conditional"]["version"] == "1.0.0"


def test_parses_pyproject_dependencies(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["httpx==0.27.0", "rich>=13.0.0"]\n'
    )
    parsed = {d["name"]: d for d in security.parse_requirements(str(tmp_path))}
    assert parsed["httpx"]["version"] == "0.27.0"
    assert parsed["rich"]["pinned"] is False
