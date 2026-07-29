"""
Behavioural (temporal) code analysis from git history.

Where the complexity, duplication and maintainability modules measure the code
as it exists *right now*, this module measures how the code has *behaved over
time*. Four metrics are derived from the commit log:

1. **Churn** — how often each file changes, and by how many lines. Heavily
   churned files are where the team actually spends its effort.
2. **Hotspots** — churn x complexity. A complicated file nobody touches is
   cheap; a complicated file that changes every week is where defects breed.
   This is the central idea of behavioural code analysis.
3. **Change coupling** — files that are repeatedly committed together. This
   surfaces *implicit* dependencies that the import graph cannot see (e.g. a
   parser and its test fixtures, or two modules that share a hidden contract).
4. **Bus factor** — how concentrated the knowledge of each file is among
   authors, i.e. how much of the codebase walks out of the door with one
   person.

Churn is exponentially time-decayed (recent changes matter more than changes
from three years ago) with a configurable half-life.

Reference:
    A. Tornhill, "Your Code as a Crime Scene", Pragmatic Bookshelf, 2015.
"""

import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from git import Repo

# --- tuning -----------------------------------------------------------------

# Commits older than this contribute half as much churn as a commit today.
CHURN_HALF_LIFE_DAYS = 180.0

# "Recent" activity window used for the at-a-glance counters.
RECENT_WINDOW_DAYS = 90

# Commits touching more files than this are almost always merges, formatting
# sweeps or vendored-dependency drops. They would couple every file to every
# other file, so they are excluded from the coupling matrix.
MAX_FILES_PER_COMMIT_FOR_COUPLING = 30

# A file pair must co-change at least this often before we believe it.
MIN_COUPLING_SUPPORT = 3

# ...and at least this fraction of the rarer file's commits.
MIN_COUPLING_DEGREE = 0.4

# Fraction of total contribution the "core" authors must cover for bus factor.
BUS_FACTOR_COVERAGE = 0.5

# A file whose top author owns this much of it is a knowledge-concentration risk.
KNOWLEDGE_RISK_SHARE = 0.75

# Below this many commits there is not enough signal to say anything.
MIN_COMMITS_FOR_ANALYSIS = 5

# Output caps, so the payload stays a sane size on huge repositories.
TOP_CHURN_FILES = 30
TOP_HOTSPOTS = 25
TOP_COUPLINGS = 30
TOP_CONTRIBUTORS = 15
TOP_AT_RISK_FILES = 20

# Field/record separators for the git log format. Chosen because they cannot
# appear in an author name, a path or a date.
_REC = "\x01"
_FLD = "\x02"


# ---------------------------------------------------------------------------
# git log parsing
# ---------------------------------------------------------------------------

def _resolve_renamed_path(raw: str) -> str:
    """
    Normalise a `--numstat` path that describes a rename.

    git emits renames as either `old.py => new.py` or, when a common prefix
    and suffix exist, `src/{old => new}/mod.py`. We always follow the *new*
    path so a renamed file keeps accumulating history under its current name.
    """
    if "=>" not in raw:
        return raw

    if "{" in raw and "}" in raw:
        prefix, rest = raw.split("{", 1)
        inner, suffix = rest.split("}", 1)
        new = inner.split("=>")[-1].strip()
        return (prefix + new + suffix).replace("//", "/").strip("/")

    return raw.split("=>")[-1].strip()


def _parse_commits(repo_path: str) -> List[Dict]:
    """
    Read the commit log into `{sha, author, email, date, files}` records.

    Only Python files are retained, and merge commits are skipped — a merge's
    numstat double-counts work already attributed to the branch commits.
    """
    repo = Repo(repo_path)
    raw = repo.git.log(
        "--no-merges",
        "--numstat",
        f"--pretty=format:{_REC}%H{_FLD}%an{_FLD}%ae{_FLD}%aI",
    )

    commits: List[Dict] = []
    for chunk in raw.split(_REC):
        chunk = chunk.strip("\n")
        if not chunk:
            continue

        header, _, body = chunk.partition("\n")
        parts = header.split(_FLD)
        if len(parts) != 4:
            continue
        sha, author, email, date_str = parts

        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            continue

        files: List[Tuple[str, int, int]] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            ins_s, del_s, path_raw = cols
            if ins_s == "-" or del_s == "-":
                continue  # binary file
            path = _resolve_renamed_path(path_raw)
            if not path.endswith(".py"):
                continue
            try:
                files.append((path, int(ins_s), int(del_s)))
            except ValueError:
                continue

        if files:
            commits.append({
                "sha": sha,
                "author": author.strip() or email.strip(),
                "email": email.strip().lower(),
                "date": date,
                "files": files,
            })

    return commits


# ---------------------------------------------------------------------------
# 1. churn
# ---------------------------------------------------------------------------

def _decay_weight(commit_date: datetime, reference: datetime) -> float:
    """Exponential time decay — a commit one half-life old counts for 0.5."""
    age_days = max(0.0, (reference - commit_date).total_seconds() / 86400.0)
    return 0.5 ** (age_days / CHURN_HALF_LIFE_DAYS)


def compute_churn(commits: Sequence[Dict], reference: datetime) -> Dict[str, Dict]:
    """Per-file change frequency, line volume, authorship and recency."""
    recent_cutoff = reference - timedelta(days=RECENT_WINDOW_DAYS)
    churn: Dict[str, Dict] = {}

    for commit in commits:
        weight = _decay_weight(commit["date"], reference)
        is_recent = commit["date"] >= recent_cutoff

        for path, insertions, deletions in commit["files"]:
            entry = churn.get(path)
            if entry is None:
                entry = churn[path] = {
                    "file_path": path,
                    "commits": 0,
                    "insertions": 0,
                    "deletions": 0,
                    "churn": 0,
                    "weighted_churn": 0.0,
                    "recent_commits": 0,
                    "authors": set(),
                    "first_modified": commit["date"],
                    "last_modified": commit["date"],
                    # author -> lines contributed, used by the bus-factor pass
                    "_by_author": defaultdict(int),
                }

            lines = insertions + deletions
            entry["commits"] += 1
            entry["insertions"] += insertions
            entry["deletions"] += deletions
            entry["churn"] += lines
            entry["weighted_churn"] += lines * weight
            entry["authors"].add(commit["author"])
            entry["_by_author"][commit["author"]] += lines
            if is_recent:
                entry["recent_commits"] += 1
            if commit["date"] < entry["first_modified"]:
                entry["first_modified"] = commit["date"]
            if commit["date"] > entry["last_modified"]:
                entry["last_modified"] = commit["date"]

    return churn


# ---------------------------------------------------------------------------
# 2. hotspots (churn x complexity)
# ---------------------------------------------------------------------------

def _normalise_churn(value: float, maximum: float) -> float:
    """
    Log-normalise churn to 0..1.

    Churn is heavily long-tailed — one generated file can have 100x the churn
    of everything else — so a linear scale would flatten every real signal to
    near zero.
    """
    if maximum <= 0:
        return 0.0
    return math.log1p(value) / math.log1p(maximum)


def _categorise(risk: float) -> str:
    if risk >= 0.50:
        return "critical"
    if risk >= 0.25:
        return "high"
    if risk >= 0.10:
        return "moderate"
    return "low"


def compute_hotspots(churn: Dict[str, Dict], complexity_by_file: Dict[str, int]) -> List[Dict]:
    """
    Rank files by `normalised churn x normalised complexity`.

    Either factor alone is a weak signal: a complex file that never changes
    costs nothing to leave alone, and a trivial file that changes constantly
    is not a problem. Their product is where refactoring actually pays.
    """
    if not churn:
        return []

    max_churn = max(e["weighted_churn"] for e in churn.values())
    max_complexity = max(complexity_by_file.values(), default=0)

    hotspots: List[Dict] = []
    for path, entry in churn.items():
        complexity = complexity_by_file.get(path)
        if complexity is None:
            continue  # deleted, or excluded from the current snapshot

        norm_churn = _normalise_churn(entry["weighted_churn"], max_churn)
        norm_complexity = (complexity / max_complexity) if max_complexity else 0.0
        risk = norm_churn * norm_complexity

        by_author = entry["_by_author"]
        primary_author, primary_lines = max(
            by_author.items(), key=lambda kv: kv[1], default=("unknown", 0)
        )
        total_lines = sum(by_author.values()) or 1

        hotspots.append({
            "file_path": path,
            "risk_score": round(risk * 100, 1),
            "category": _categorise(risk),
            "complexity": complexity,
            "churn": entry["churn"],
            "commits": entry["commits"],
            "recent_commits": entry["recent_commits"],
            "author_count": len(entry["authors"]),
            "primary_author": primary_author,
            "primary_author_share": round(primary_lines / total_lines * 100, 1),
            "last_modified": entry["last_modified"].date().isoformat(),
        })

    hotspots.sort(key=lambda h: h["risk_score"], reverse=True)
    return hotspots[:TOP_HOTSPOTS]


# ---------------------------------------------------------------------------
# 3. temporal change coupling
# ---------------------------------------------------------------------------

def compute_coupling(commits: Sequence[Dict], churn: Dict[str, Dict]) -> List[Dict]:
    """
    Find file pairs that are habitually committed together.

    `degree` is the conditional probability of co-change: of the commits that
    touched the *less frequently changed* file of the pair, what fraction also
    touched the other one. Normalising by the rarer file stops a hot file like
    `settings.py` from looking coupled to everything.
    """
    co_changes: Dict[Tuple[str, str], int] = defaultdict(int)

    for commit in commits:
        paths = sorted({path for path, _, _ in commit["files"]})
        if not 2 <= len(paths) <= MAX_FILES_PER_COMMIT_FOR_COUPLING:
            continue
        for i, a in enumerate(paths):
            for b in paths[i + 1:]:
                co_changes[(a, b)] += 1

    couplings: List[Dict] = []
    for (a, b), shared in co_changes.items():
        if shared < MIN_COUPLING_SUPPORT:
            continue
        commits_a = churn[a]["commits"]
        commits_b = churn[b]["commits"]
        degree = shared / min(commits_a, commits_b)
        if degree < MIN_COUPLING_DEGREE:
            continue
        union = commits_a + commits_b - shared
        couplings.append({
            "file_a": a,
            "file_b": b,
            "co_changes": shared,
            "commits_a": commits_a,
            "commits_b": commits_b,
            "degree": round(degree * 100, 1),
            "jaccard": round(shared / union * 100, 1) if union else 0.0,
        })

    couplings.sort(key=lambda c: (c["degree"], c["co_changes"]), reverse=True)
    return couplings[:TOP_COUPLINGS]


# ---------------------------------------------------------------------------
# 4. bus factor / knowledge distribution
# ---------------------------------------------------------------------------

def _bus_factor(contributions: Dict[str, int]) -> int:
    """Smallest number of authors whose combined work covers 50% of the lines."""
    total = sum(contributions.values())
    if total <= 0:
        return 0
    covered = 0
    for index, lines in enumerate(sorted(contributions.values(), reverse=True), start=1):
        covered += lines
        if covered / total >= BUS_FACTOR_COVERAGE:
            return index
    return len(contributions)


def compute_bus_factor(commits: Sequence[Dict], churn: Dict[str, Dict]) -> Dict:
    """Repository-wide and per-file knowledge concentration."""
    repo_lines: Dict[str, int] = defaultdict(int)
    repo_commits: Dict[str, int] = defaultdict(int)
    last_seen: Dict[str, datetime] = {}

    for commit in commits:
        author = commit["author"]
        repo_commits[author] += 1
        repo_lines[author] += sum(ins + dels for _, ins, dels in commit["files"])
        if author not in last_seen or commit["date"] > last_seen[author]:
            last_seen[author] = commit["date"]

    total_lines = sum(repo_lines.values()) or 1
    contributors = [
        {
            "author": author,
            "commits": repo_commits[author],
            "lines": lines,
            "share": round(lines / total_lines * 100, 1),
            "last_active": last_seen[author].date().isoformat(),
        }
        for author, lines in sorted(repo_lines.items(), key=lambda kv: kv[1], reverse=True)
    ]

    at_risk: List[Dict] = []
    for path, entry in churn.items():
        by_author = entry["_by_author"]
        file_total = sum(by_author.values())
        if not file_total or entry["commits"] < 2:
            continue
        primary_author, primary_lines = max(by_author.items(), key=lambda kv: kv[1])
        share = primary_lines / file_total
        if share < KNOWLEDGE_RISK_SHARE:
            continue
        at_risk.append({
            "file_path": path,
            "primary_author": primary_author,
            "primary_author_share": round(share * 100, 1),
            "author_count": len(by_author),
            "commits": entry["commits"],
            "churn": entry["churn"],
            "bus_factor": _bus_factor(by_author),
        })

    # Rank by how much code is locked behind one person, not just by share.
    at_risk.sort(key=lambda f: (f["primary_author_share"], f["churn"]), reverse=True)

    return {
        "repository_bus_factor": _bus_factor(repo_lines),
        "contributor_count": len(repo_lines),
        "top_contributors": contributors[:TOP_CONTRIBUTORS],
        "at_risk_files": at_risk[:TOP_AT_RISK_FILES],
        "at_risk_count": len(at_risk),
    }


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def _empty_report(reason: str) -> Dict:
    return {
        "available": False,
        "reason": reason,
        "commits_analyzed": 0,
        "contributor_count": 0,
        "period_days": 0,
        "first_commit": None,
        "last_commit": None,
        "churn_files": [],
        "hotspots": [],
        "coupling": [],
        "bus_factor": {
            "repository_bus_factor": 0,
            "contributor_count": 0,
            "top_contributors": [],
            "at_risk_files": [],
            "at_risk_count": 0,
        },
        "summary": {
            "critical_hotspots": 0,
            "high_hotspots": 0,
            "coupled_pairs": 0,
            "knowledge_risk_files": 0,
        },
    }


def analyze(repo_path: str, complexity_by_file: Optional[Dict[str, int]] = None) -> Dict:
    """
    Run the full behavioural analysis over a cloned repository.

    `complexity_by_file` maps repo-relative path -> total cyclomatic complexity
    and is what turns raw churn into a hotspot ranking. History analysis is
    strictly best-effort: a shallow clone, an empty repo or a git failure
    degrades to an "unavailable" report rather than failing the whole run.
    """
    complexity_by_file = {
        path.replace("\\", "/"): value
        for path, value in (complexity_by_file or {}).items()
    }

    try:
        commits = _parse_commits(repo_path)
    except Exception as e:  # not a git repo, corrupt objects, git missing...
        return _empty_report(f"Could not read git history: {e}")

    if len(commits) < MIN_COMMITS_FOR_ANALYSIS:
        return _empty_report(
            f"Only {len(commits)} commit(s) with Python changes available — "
            f"at least {MIN_COMMITS_FOR_ANALYSIS} are needed for behavioural analysis."
        )

    # Anchor "now" to the newest commit rather than wall-clock time, so the
    # same clone always produces the same decay weights.
    reference = max(c["date"] for c in commits)
    oldest = min(c["date"] for c in commits)

    churn = compute_churn(commits, reference)
    hotspots = compute_hotspots(churn, complexity_by_file)
    coupling = compute_coupling(commits, churn)
    bus_factor = compute_bus_factor(commits, churn)

    churn_files = sorted(
        (
            {
                "file_path": e["file_path"],
                "commits": e["commits"],
                "insertions": e["insertions"],
                "deletions": e["deletions"],
                "churn": e["churn"],
                "weighted_churn": round(e["weighted_churn"], 1),
                "recent_commits": e["recent_commits"],
                "author_count": len(e["authors"]),
                "first_modified": e["first_modified"].date().isoformat(),
                "last_modified": e["last_modified"].date().isoformat(),
            }
            for e in churn.values()
        ),
        key=lambda f: f["churn"],
        reverse=True,
    )

    return {
        "available": True,
        "reason": None,
        "commits_analyzed": len(commits),
        "contributor_count": bus_factor["contributor_count"],
        "period_days": max(1, (reference - oldest).days),
        "first_commit": oldest.date().isoformat(),
        "last_commit": reference.date().isoformat(),
        "churn_files": churn_files[:TOP_CHURN_FILES],
        "hotspots": hotspots,
        "coupling": coupling,
        "bus_factor": bus_factor,
        "summary": {
            "critical_hotspots": sum(1 for h in hotspots if h["category"] == "critical"),
            "high_hotspots": sum(1 for h in hotspots if h["category"] == "high"),
            "coupled_pairs": len(coupling),
            "knowledge_risk_files": bus_factor["at_risk_count"],
        },
    }
