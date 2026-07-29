"""
Security scanning.

Three independent passes, reported under one panel:

1. **Vulnerability patterns** — an AST walk for dangerous constructs
   (`eval`, `shell=True`, unsafe deserialisation, disabled TLS verification,
   string-built SQL, weak hashes...). Working on the AST rather than on regex
   over raw text means `# eval(x)` in a comment or `"exec"` in a docstring do
   not produce false positives.

2. **Hardcoded secrets** — string literals that look like credentials, found
   three ways: assignment to a secret-shaped variable name, known provider
   token prefixes (AWS, GitHub, Slack, Google, OpenAI, PEM blocks), and
   Shannon-entropy analysis for high-randomness strings that match no known
   format. Matched values are redacted before they reach the report.

3. **Vulnerable dependencies** — declared requirements are checked against the
   OSV.dev vulnerability database (https://osv.dev), the same data source used
   by `pip-audit` and GitHub's advisory database.

Severity follows the usual critical/high/medium/low ladder and rolls up into a
0-100 security score.
"""

import ast
import math
import os
import re
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

import httpx

# --- scoring ----------------------------------------------------------------

SEVERITY_ORDER = ["critical", "high", "medium", "low"]

# Penalty points contributed to the security score by one finding.
SEVERITY_PENALTY = {"critical": 15.0, "high": 8.0, "medium": 3.0, "low": 1.0}

# Penalty at which the security score halves. Accumulated penalty is applied as
# exponential decay rather than straight subtraction: a linear scale bottoms
# out at zero after a handful of findings, after which a repository with five
# problems and one with fifty look identical.
SECURITY_SCORE_HALF_LIFE = 20.0

# Code findings are scored as a *density* per this many lines, so the score
# stays comparable between a 500-line script and a 50,000-line service. Scoring
# them absolutely would mean any large codebase reads as catastrophic purely
# because there is more of it.
DENSITY_BASELINE_LOC = 1000.0

# Dependency advisories are not scored by density — a vulnerable package is
# equally exploitable whether the project around it is large or small — so they
# contribute their raw penalty. They are counted once per *package* at its worst
# severity rather than once per advisory, because a single version bump clears
# every advisory against that package; charging eight times for eight CVEs in
# one dependency would measure paperwork rather than remediation effort.

# --- secret detection tuning ------------------------------------------------

SECRET_NAME_PATTERN = re.compile(
    r"(pass(word|wd)?|secret|token|api[_-]?key|apikey|access[_-]?key|"
    r"private[_-]?key|client[_-]?secret|auth[_-]?(token|key)|credential|salt)",
    re.IGNORECASE,
)

# Names that merely *describe* a credential rather than holding one. Without
# these, `GITHUB_TOKEN_URL = "https://..."` reads as a leaked token.
SECRET_NAME_EXCLUSIONS = re.compile(
    r"(_|^)(url|uri|endpoint|path|file|dir|header|prefix|suffix|pattern|regex|"
    r"field|param|name|label|type|algorithm|scheme|format|template|env|var|"
    r"placeholder|example|column|attr|arg|kwarg)s?$",
    re.IGNORECASE,
)

# Values that match a secret-shaped name but are obviously not real secrets.
PLACEHOLDER_PATTERN = re.compile(
    r"^\s*$|^(none|null|todo|tbd|placeholder|example|"
    r"xxx+|\.\.\.|test|dummy|fake|sample|<.*>|\$\{.*\}|%\(.*\)s|\{.*\})\s*$",
    re.IGNORECASE,
)

# Substrings that mark a value as a stand-in wherever they appear inside it,
# e.g. "change-me-in-production" or "your_api_key_here".
PLACEHOLDER_SUBSTRINGS = (
    "changeme", "change-me", "change_me", "your-", "your_", "yourkey", "replace-me",
    "replace_me", "insert-", "insert_", "placeholder", "example.com", "xxxxx",
    "notasecret", "dummy", "<", ">", "${", "{{",
)

# A URL is not a credential — unless it embeds one, which the connection-string
# signature below catches separately.
URL_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)

MIN_SECRET_LENGTH = 8

# Entropy scan: only strings this long, this random, and this "key-like".
MIN_ENTROPY_LENGTH = 20
MIN_ENTROPY_BITS = 4.0
KEYLIKE_PATTERN = re.compile(r"^[A-Za-z0-9+/=_\-]+$")

# Known credential formats. Ordered most-specific first.
TOKEN_SIGNATURES: List[Tuple[str, re.Pattern, str]] = [
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"), "critical"),
    ("aws_access_key", re.compile(r"\b(A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}\b"), "critical"),
    ("github_token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "critical"),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "critical"),
    ("stripe_key", re.compile(r"\b(sk|rk)_(live|test)_[A-Za-z0-9]{20,}\b"), "critical"),
    ("openai_key", re.compile(r"\bsk-(proj-)?[A-Za-z0-9_-]{20,}\b"), "critical"),
    ("google_api_key", re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"), "high"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\b"), "high"),
    ("connection_string", re.compile(r"\b(postgres|postgresql|mysql|mongodb(\+srv)?|redis|amqp)://[^\s:@/]+:[^\s:@/]+@"), "high"),
]

# --- dependency scanning ----------------------------------------------------

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns"
OSV_TIMEOUT_SECONDS = 12.0
MAX_DEPENDENCIES_QUERIED = 200
MAX_VULN_DETAILS_FETCHED = 30

# `==` is an exact pin; `>=` / `~=` give the *lowest* version the project
# accepts, which is still the right thing to check — an advisory affecting the
# floor affects anyone who installs it.
REQUIREMENT_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(==|>=|~=)\s*([A-Za-z0-9][A-Za-z0-9.*+!-]*)"
)

# Map OSV / advisory severity words onto our ladder.
OSV_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MODERATE": "medium",
    "MEDIUM": "medium",
    "LOW": "low",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def shannon_entropy(value: str) -> float:
    """Shannon entropy in bits per character — the randomness of a string."""
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _is_placeholder(value: str) -> bool:
    """True for stand-in values that only look like credentials."""
    if PLACEHOLDER_PATTERN.match(value):
        return True
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_SUBSTRINGS)


def _redact(value: str) -> str:
    """Never echo a live credential back into a report."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 8}{value[-2:]}"


def _attr_chain(node: ast.AST) -> str:
    """Render `a.b.c` from an Attribute/Name node, or '' if it is neither."""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _keyword(call: ast.Call, name: str) -> Optional[ast.expr]:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_true(node: Optional[ast.expr]) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_false(node: Optional[ast.expr]) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _issue(line: int, rule: str, severity: str, title: str, message: str,
           recommendation: str, cwe: Optional[str] = None) -> Dict:
    return {
        "line": line,
        "rule": rule,
        "severity": severity,
        "title": title,
        "message": message,
        "recommendation": recommendation,
        "cwe": cwe,
    }


# ---------------------------------------------------------------------------
# 1. vulnerability patterns
# ---------------------------------------------------------------------------

def _check_call(node: ast.Call) -> List[Dict]:
    """Match one call expression against the dangerous-construct rules."""
    issues: List[Dict] = []
    func = _attr_chain(node.func)
    simple = node.func.id if isinstance(node.func, ast.Name) else func.split(".")[-1]
    line = node.lineno

    if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
        issues.append(_issue(
            line, "dangerous_eval", "critical",
            f"Use of {node.func.id}()",
            f"`{node.func.id}()` executes arbitrary code; if any part of its input is "
            "attacker-controlled this is remote code execution.",
            "Parse the value explicitly instead — `ast.literal_eval()` for data, or a "
            "dispatch dict for behaviour.",
            "CWE-95",
        ))

    if func in ("os.system", "os.popen", "commands.getoutput", "commands.getstatusoutput"):
        issues.append(_issue(
            line, "shell_command", "high",
            f"Shell execution via {func}()",
            f"`{func}()` passes its argument to a shell, so any interpolated value can "
            "inject additional commands.",
            "Use `subprocess.run([...])` with an argument list and no shell.",
            "CWE-78",
        ))

    if func.startswith("subprocess.") and _is_true(_keyword(node, "shell")):
        issues.append(_issue(
            line, "subprocess_shell", "high",
            "subprocess called with shell=True",
            "`shell=True` runs the command through /bin/sh, allowing command injection "
            "if any part of the command is built from untrusted input.",
            "Pass the command as a list and drop `shell=True`.",
            "CWE-78",
        ))

    if func in ("pickle.load", "pickle.loads", "cPickle.load", "cPickle.loads",
                "dill.load", "dill.loads", "shelve.open",
                "marshal.load", "marshal.loads", "jsonpickle.decode"):
        issues.append(_issue(
            line, "unsafe_deserialization", "high",
            f"Unsafe deserialisation via {func}()",
            "Deserialising untrusted data with this module can execute arbitrary code "
            "during unpickling.",
            "Use JSON for untrusted data, or sign the payload and verify before loading.",
            "CWE-502",
        ))

    if func in ("yaml.load", "yaml.load_all"):
        loader = _keyword(node, "Loader")
        loader_name = _attr_chain(loader) if loader is not None else ""
        if loader is None or "Safe" not in loader_name:
            issues.append(_issue(
                line, "unsafe_yaml", "high",
                "yaml.load() without SafeLoader",
                "The default YAML loader can instantiate arbitrary Python objects, which "
                "makes loading untrusted YAML equivalent to running it.",
                "Use `yaml.safe_load()`, or pass `Loader=yaml.SafeLoader`.",
                "CWE-502",
            ))

    # `usedforsecurity=False` (Python 3.9+) is the explicit way to say this hash
    # is a checksum or a fingerprint, not a security control.
    if func in ("hashlib.md5", "hashlib.sha1") and not _is_false(_keyword(node, "usedforsecurity")):
        algorithm = func.split(".")[1]
        issues.append(_issue(
            line, "weak_hash", "medium",
            f"Weak hash algorithm ({algorithm})",
            f"{algorithm.upper()} is collision-prone and unsuitable for signatures, "
            "integrity checks or password storage.",
            "Use SHA-256+ for integrity, and bcrypt/argon2/scrypt for passwords. If this "
            "hash is only a non-security fingerprint, pass `usedforsecurity=False`.",
            "CWE-327",
        ))

    if func == "tempfile.mktemp":
        issues.append(_issue(
            line, "insecure_temp_file", "medium",
            "Insecure temporary file",
            "`mktemp()` only reserves a name; another process can create that path "
            "before you open it (a TOCTOU race).",
            "Use `tempfile.mkstemp()` or `NamedTemporaryFile()`.",
            "CWE-377",
        ))

    if _is_false(_keyword(node, "verify")) and (
        func.startswith("requests.") or func.startswith("httpx.") or simple in ("get", "post", "put", "patch", "delete", "request")
    ):
        issues.append(_issue(
            line, "tls_verification_disabled", "high",
            "TLS certificate verification disabled",
            "`verify=False` accepts any certificate, which removes protection against "
            "man-in-the-middle interception.",
            "Leave verification on; point `verify` at your CA bundle if you use a private CA.",
            "CWE-295",
        ))

    if func in ("ssl._create_unverified_context",):
        issues.append(_issue(
            line, "tls_verification_disabled", "high",
            "Unverified SSL context",
            "This context performs no certificate or hostname validation.",
            "Use `ssl.create_default_context()`.",
            "CWE-295",
        ))

    if simple in ("execute", "executemany", "executescript", "raw") and node.args:
        first = node.args[0]
        # Unwrap SQLAlchemy's `execute(text("..."))` so the string inside is
        # what gets inspected. Matching on `text(...)` directly would fire on
        # every unrelated function that happens to be called `text`.
        if isinstance(first, ast.Call) and isinstance(first.func, ast.Name) and first.func.id in ("text", "sql"):
            if first.args:
                first = first.args[0]
        built_dynamically = (
            isinstance(first, ast.JoinedStr)  # f-string
            or (isinstance(first, ast.BinOp) and isinstance(first.op, (ast.Add, ast.Mod)))
            or (isinstance(first, ast.Call) and isinstance(first.func, ast.Attribute)
                and first.func.attr == "format")
        )
        if built_dynamically:
            issues.append(_issue(
                line, "sql_injection", "critical",
                "SQL query built by string interpolation",
                "Building SQL with an f-string, `%`, `+` or `.format()` lets input change "
                "the structure of the query.",
                "Use parameterised queries: `execute(\"... WHERE id = ?\", (value,))`.",
                "CWE-89",
            ))

    if simple == "run" and _is_true(_keyword(node, "debug")):
        issues.append(_issue(
            line, "debug_enabled", "medium",
            "Debug mode enabled",
            "A debug server exposes tracebacks and, in Flask's case, an interactive "
            "console that executes code.",
            "Drive this from an environment variable and default it to off.",
            "CWE-489",
        ))

    if func in ("os.chmod",) and len(node.args) >= 2:
        mode = node.args[1]
        if isinstance(mode, ast.Constant) and isinstance(mode.value, int) and mode.value & 0o002:
            issues.append(_issue(
                line, "world_writable", "medium",
                "World-writable permissions",
                f"Mode {oct(mode.value)} lets any local user modify this path.",
                "Restrict the mode — 0o600 for secrets, 0o644 for readable data.",
                "CWE-732",
            ))

    if func in ("xml.etree.ElementTree.fromstring", "xml.etree.ElementTree.parse",
                "xml.dom.minidom.parse", "xml.dom.minidom.parseString", "xml.sax.parse"):
        issues.append(_issue(
            line, "xml_external_entity", "medium",
            "XML parsed with a non-hardened parser",
            "Python's stdlib XML parsers can be induced to resolve external entities or "
            "expand nested entities (billion laughs).",
            "Use `defusedxml` for untrusted XML.",
            "CWE-611",
        ))

    return issues


def detect_code_issues(source: str) -> List[Dict]:
    """AST scan of one file for dangerous constructs."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    issues: List[Dict] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            issues.extend(_check_call(node))

        elif isinstance(node, ast.Assert):
            issues.append(_issue(
                node.lineno, "assert_for_validation", "low",
                "assert used outside a test",
                "`assert` statements are removed entirely when Python runs with -O, so "
                "any check implemented this way silently disappears in production.",
                "Raise an explicit exception instead.",
                "CWE-617",
            ))

    return issues


def _is_test_file(file_path: str) -> bool:
    name = os.path.basename(file_path)
    normalised = f"/{file_path.replace(os.sep, '/')}/"
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or "/tests/" in normalised
        or "/test/" in normalised
    )


def _downgrade(severity: str) -> str:
    """Drop a finding one rung down the severity ladder."""
    index = SEVERITY_ORDER.index(severity)
    return SEVERITY_ORDER[min(index + 1, len(SEVERITY_ORDER) - 1)]


# ---------------------------------------------------------------------------
# 2. hardcoded secrets
# ---------------------------------------------------------------------------

def _signature_match(value: str) -> Optional[Tuple[str, str]]:
    for name, pattern, severity in TOKEN_SIGNATURES:
        if pattern.search(value):
            return name, severity
    return None


def detect_secrets(source: str) -> List[Dict]:
    """
    Find credential-looking string literals.

    Walks assignments (so the variable *name* can inform the decision) and then
    every remaining string constant (so a bare token still gets caught).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    findings: List[Dict] = []
    reported: set = set()  # (line, redacted value) — one finding per literal

    def record(line: int, value: str, rule: str, severity: str, title: str, message: str) -> None:
        key = (line, value[:16])
        if key in reported:
            return
        reported.add(key)
        findings.append({
            **_issue(line, rule, severity, title, message,
                     "Move the value into an environment variable or a secret manager, "
                     "then rotate it — git history keeps the old value forever.",
                     "CWE-798"),
            "match": _redact(value),
        })

    # Pass 1: named assignments, e.g. API_KEY = "..."
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value_node = node.value
        if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
            continue

        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            name = target.id if isinstance(target, ast.Name) else (
                target.attr if isinstance(target, ast.Attribute) else ""
            )
            if not name or not SECRET_NAME_PATTERN.search(name):
                continue
            if SECRET_NAME_EXCLUSIONS.search(name):
                continue  # e.g. GITHUB_TOKEN_URL holds a URL, not a token

            literal = value_node.value
            if len(literal) < MIN_SECRET_LENGTH or _is_placeholder(literal):
                continue
            if URL_PATTERN.match(literal):
                continue

            record(
                value_node.lineno, literal, "hardcoded_secret", "high",
                f"Hardcoded secret in '{name}'",
                f"`{name}` is assigned a literal string. Anything committed here is "
                "readable by everyone with repository access.",
            )

    # Pass 2: every string constant — known formats, then entropy.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        literal = node.value

        signature = _signature_match(literal)
        if signature:
            rule_name, severity = signature
            record(
                node.lineno, literal, f"exposed_{rule_name}", severity,
                f"Exposed credential ({rule_name.replace('_', ' ')})",
                f"This literal matches the known format of a {rule_name.replace('_', ' ')}.",
            )
            continue

        if (
            len(literal) >= MIN_ENTROPY_LENGTH
            and KEYLIKE_PATTERN.match(literal)
            and not _is_placeholder(literal)
            and shannon_entropy(literal) >= MIN_ENTROPY_BITS
        ):
            record(
                node.lineno, literal, "high_entropy_string", "medium",
                "High-entropy string literal",
                f"This {len(literal)}-character string has an entropy of "
                f"{shannon_entropy(literal):.1f} bits/char, which is characteristic of a "
                "key or token rather than of ordinary text.",
            )

    return findings


# ---------------------------------------------------------------------------
# 3. vulnerable dependencies (OSV.dev)
# ---------------------------------------------------------------------------

def parse_requirements(root_dir: str) -> List[Dict]:
    """
    Collect declared dependencies from requirements files and pyproject.toml.

    OSV needs a concrete version to decide whether a package falls inside an
    advisory's affected range, so only requirements carrying one are usable.
    Exact pins are checked as-is; `>=` and `~=` constraints are checked at their
    lower bound and flagged as unpinned in the report, because that is the
    oldest version the project will actually install.
    """
    found: Dict[Tuple[str, str], Dict] = {}

    def add(name: str, version: str, operator: str, source: str) -> None:
        found.setdefault((name, version), {
            "name": name,
            "version": version,
            "pinned": operator == "==",
            "constraint": f"{operator}{version}",
            "source": source,
        })

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".venv", "venv", "__pycache__"}]
        for fname in filenames:
            path = os.path.join(dirpath, fname)
            rel = os.path.relpath(path, root_dir).replace(os.sep, "/")

            if fname.endswith(".txt") and "requirements" in fname.lower():
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                except OSError:
                    continue
                for raw in lines:
                    line = raw.split("#")[0].split(";")[0].strip()
                    match = REQUIREMENT_PATTERN.match(line)
                    if match:
                        add(match.group(1).lower(), match.group(3), match.group(2), rel)

            elif fname == "pyproject.toml":
                for name, version, operator in _parse_pyproject(path):
                    add(name, version, operator, rel)

    return list(found.values())[:MAX_DEPENDENCIES_QUERIED]


def _parse_pyproject(path: str) -> List[Tuple[str, str, str]]:
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        return []

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []

    specs: List[str] = []
    project = data.get("project", {})
    if isinstance(project.get("dependencies"), list):
        specs.extend(str(d) for d in project["dependencies"])
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in optional.values():
            if isinstance(group, list):
                specs.extend(str(d) for d in group)

    # Poetry writes `name = "^1.2.3"`. Caret and tilde ranges pin the lower
    # bound, so rewrite them into a form the shared pattern understands.
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry, dict):
        for name, constraint in poetry.items():
            if not isinstance(constraint, str) or name.lower() == "python":
                continue
            if constraint.startswith(("^", "~")):
                specs.append(f"{name}>={constraint[1:]}")
            elif constraint[:2] in ("==", ">=", "~="):
                specs.append(f"{name}{constraint}")

    parsed: List[Tuple[str, str, str]] = []
    for spec in specs:
        match = REQUIREMENT_PATTERN.match(spec.split(";")[0].strip())
        if match:
            parsed.append((match.group(1).lower(), match.group(3), match.group(2)))
    return parsed


def _osv_severity(vuln: Dict) -> str:
    """Pull a severity word out of an OSV record, which has several shapes."""
    specific = vuln.get("database_specific", {})
    if isinstance(specific, dict):
        word = str(specific.get("severity", "")).upper()
        if word in OSV_SEVERITY_MAP:
            return OSV_SEVERITY_MAP[word]

    for entry in vuln.get("severity", []) or []:
        score = str(entry.get("score", ""))
        # CVSS v3 vector — derive a band from the base metrics we can read.
        if "AV:N" in score and "C:H" in score:
            return "critical"
        if "C:H" in score or "I:H" in score:
            return "high"

    for affected in vuln.get("affected", []) or []:
        specific = affected.get("database_specific", {})
        if isinstance(specific, dict):
            word = str(specific.get("severity", "")).upper()
            if word in OSV_SEVERITY_MAP:
                return OSV_SEVERITY_MAP[word]

    return "medium"


def _fixed_versions(vuln: Dict, package: str) -> List[str]:
    fixes: List[str] = []
    for affected in vuln.get("affected", []) or []:
        if affected.get("package", {}).get("name", "").lower() != package:
            continue
        for entry in affected.get("ranges", []) or []:
            for event in entry.get("events", []) or []:
                if "fixed" in event:
                    fixes.append(event["fixed"])
    return sorted(set(fixes))[:3]


def scan_dependencies(root_dir: str) -> Dict:
    """
    Query OSV.dev for advisories affecting the pinned dependencies.

    Network access is best-effort: if OSV is unreachable the panel reports
    itself as unavailable instead of failing the analysis.
    """
    dependencies = parse_requirements(root_dir)
    if not dependencies:
        return {
            "available": False,
            "reason": "No versioned dependencies found — a requirements file or pyproject.toml "
                      "with `==`, `>=` or `~=` constraints is needed to check advisories.",
            "dependencies_checked": 0,
            "unpinned_count": 0,
            "vulnerabilities": [],
            "vulnerable_package_count": 0,
        }

    queries = [
        {"package": {"name": d["name"], "ecosystem": "PyPI"}, "version": d["version"]}
        for d in dependencies
    ]

    try:
        with httpx.Client(timeout=OSV_TIMEOUT_SECONDS) as client:
            response = client.post(OSV_BATCH_URL, json={"queries": queries})
            response.raise_for_status()
            results = response.json().get("results", [])

            # querybatch returns IDs only; fetch details for a bounded number.
            wanted: List[Tuple[Dict, str]] = []
            for dependency, result in zip(dependencies, results):
                for vuln in (result or {}).get("vulns", []) or []:
                    if len(wanted) >= MAX_VULN_DETAILS_FETCHED:
                        break
                    wanted.append((dependency, vuln["id"]))

            vulnerabilities: List[Dict] = []
            for dependency, vuln_id in wanted:
                try:
                    detail = client.get(f"{OSV_VULN_URL}/{vuln_id}")
                    detail.raise_for_status()
                    vuln = detail.json()
                except Exception:
                    vuln = {"id": vuln_id, "summary": "Advisory details unavailable."}

                aliases = [a for a in vuln.get("aliases", []) if a.startswith("CVE-")]
                vulnerabilities.append({
                    "package": dependency["name"],
                    "version": dependency["version"],
                    "pinned": dependency["pinned"],
                    "constraint": dependency["constraint"],
                    "source": dependency["source"],
                    "vulnerability_id": vuln.get("id", vuln_id),
                    "cve": aliases[0] if aliases else None,
                    "severity": _osv_severity(vuln),
                    "summary": (vuln.get("summary") or vuln.get("details", "") or "")[:300].strip(),
                    "fixed_versions": _fixed_versions(vuln, dependency["name"]),
                    "reference": f"https://osv.dev/vulnerability/{vuln.get('id', vuln_id)}",
                })
    except Exception as e:
        return {
            "available": False,
            "reason": f"Could not reach the OSV vulnerability database: {e}",
            "dependencies_checked": len(dependencies),
            "unpinned_count": sum(1 for d in dependencies if not d["pinned"]),
            "vulnerabilities": [],
            "vulnerable_package_count": 0,
        }

    vulnerabilities.sort(key=lambda v: SEVERITY_ORDER.index(v["severity"]))

    return {
        "available": True,
        "reason": None,
        "dependencies_checked": len(dependencies),
        "unpinned_count": sum(1 for d in dependencies if not d["pinned"]),
        "vulnerabilities": vulnerabilities,
        "vulnerable_package_count": len({v["package"] for v in vulnerabilities}),
    }


# ---------------------------------------------------------------------------
# scoring + orchestration
# ---------------------------------------------------------------------------

def _penalty(counts: Dict[str, int]) -> float:
    return sum(SEVERITY_PENALTY[sev] * counts.get(sev, 0) for sev in SEVERITY_ORDER)


def compute_security_score(code_counts: Dict[str, int],
                           dependency_counts: Optional[Dict[str, int]] = None,
                           total_loc: int = 0) -> float:
    """
    0-100 security score: 100 for a clean repository, decaying with severity.

    Code findings are converted to a penalty *density* per
    `DENSITY_BASELINE_LOC` lines so the score means the same thing at any
    codebase size; dependency advisories contribute their raw penalty, since a
    vulnerable package is no less exploitable in a big project. The combined
    penalty then halves the score every `SECURITY_SCORE_HALF_LIFE` points —
    exponential decay rather than subtraction, so heavily-affected repositories
    stay distinguishable instead of all bottoming out at zero.
    """
    code_penalty = _penalty(code_counts)
    if total_loc > 0:
        code_penalty = code_penalty / total_loc * DENSITY_BASELINE_LOC

    total = code_penalty + _penalty(dependency_counts or {})
    return round(100.0 * 0.5 ** (total / SECURITY_SCORE_HALF_LIFE), 1)


def analyze(files: Sequence[Tuple[str, str]], root_dir: Optional[str] = None,
            scan_deps: bool = True, total_loc: int = 0) -> Dict:
    """
    Run all three passes over the repository.

    `files` is the shared `(relative_path, source)` list built once by the
    orchestrator, so no file is read twice. `total_loc` lets code findings be
    scored as a density rather than an absolute count.
    """
    file_reports: List[Dict] = []
    counts: Counter = Counter()
    test_issue_count = 0

    for rel_path, source in files:
        is_test = _is_test_file(rel_path)
        issues = detect_code_issues(source)

        # `assert` is the whole point of a test, not a bug.
        if is_test:
            issues = [i for i in issues if i["rule"] != "assert_for_validation"]

        issues.extend(detect_secrets(source))
        if not issues:
            continue

        # Test code is not shipped attack surface. `pickle.loads` and
        # `verify=False` in a test suite are usually exercising the very
        # behaviour they flag, so findings there are recorded and labelled but
        # dropped one severity rung — otherwise a large test suite drowns out
        # every real finding in the production code.
        for issue in issues:
            issue["in_test"] = is_test
            if is_test:
                issue["severity"] = _downgrade(issue["severity"])

        issues.sort(key=lambda i: (SEVERITY_ORDER.index(i["severity"]), i["line"]))
        for issue in issues:
            counts[issue["severity"]] += 1
        if is_test:
            test_issue_count += len(issues)

        file_reports.append({
            "file_path": rel_path,
            "issues": issues,
            "issue_count": len(issues),
            "highest_severity": issues[0]["severity"],
            "is_test": is_test,
        })

    # Production files first, then by severity — the ordering a reviewer wants.
    file_reports.sort(
        key=lambda f: (f["is_test"], SEVERITY_ORDER.index(f["highest_severity"]), -f["issue_count"])
    )

    dependencies = (
        scan_dependencies(root_dir) if (scan_deps and root_dir)
        else {"available": False, "reason": "Dependency scanning is disabled.",
              "dependencies_checked": 0, "unpinned_count": 0,
              "vulnerabilities": [], "vulnerable_package_count": 0}
    )
    code_counts = {sev: counts.get(sev, 0) for sev in SEVERITY_ORDER}

    # Worst severity seen per package — one upgrade clears all of its advisories.
    worst_by_package: Dict[str, str] = {}
    for vuln in dependencies["vulnerabilities"]:
        counts[vuln["severity"]] += 1
        current = worst_by_package.get(vuln["package"])
        if current is None or SEVERITY_ORDER.index(vuln["severity"]) < SEVERITY_ORDER.index(current):
            worst_by_package[vuln["package"]] = vuln["severity"]

    dependency_counts: Counter = Counter(worst_by_package.values())

    severity_counts = {sev: counts.get(sev, 0) for sev in SEVERITY_ORDER}
    total = sum(severity_counts.values())

    return {
        "files": file_reports,
        "dependencies": dependencies,
        "severity_counts": severity_counts,
        "total_issues": total,
        "test_issues": test_issue_count,
        "affected_files": len(file_reports),
        "security_score": compute_security_score(code_counts, dependency_counts, total_loc),
    }
