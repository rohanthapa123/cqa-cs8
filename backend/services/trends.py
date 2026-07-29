"""
Trends and regression diffs.

Every analysis run persists a small, flat snapshot of its headline metrics.
Comparing two snapshots turns a one-off report into a direction of travel:
"duplication is up 3 points and two new high-risk functions appeared since
last Tuesday" is actionable in a way that "duplication is 12%" is not.

Each tracked metric declares which way is *better* — maintainability rising is
good, complexity rising is not — and a threshold below which a change is noise
rather than a regression. A run is only labelled a regression when at least one
metric moves the wrong way by more than its threshold, so ordinary churn does
not cry wolf.
"""

from typing import Dict, List, Optional, Sequence

# --- tracked metrics --------------------------------------------------------
# `threshold` is the smallest change worth reporting, in the metric's own unit.

METRICS: Dict[str, Dict] = {
    "health_score": {
        "label": "Health score", "unit": "/100",
        "higher_is_better": True, "threshold": 2.0, "headline": True,
    },
    "average_maintainability": {
        "label": "Maintainability index", "unit": "",
        "higher_is_better": True, "threshold": 2.0, "headline": True,
    },
    "average_complexity": {
        "label": "Average complexity", "unit": "",
        "higher_is_better": False, "threshold": 0.3, "headline": True,
    },
    "duplication_percentage": {
        "label": "Duplicate code", "unit": "%",
        "higher_is_better": False, "threshold": 1.0, "headline": True,
    },
    "security_score": {
        "label": "Security score", "unit": "/100",
        "higher_is_better": True, "threshold": 3.0, "headline": True,
    },
    "type_hint_coverage": {
        "label": "Type hint coverage", "unit": "%",
        "higher_is_better": True, "threshold": 2.0, "headline": True,
    },
    "high_risk_functions": {
        "label": "High-risk functions", "unit": "",
        "higher_is_better": False, "threshold": 0.5, "headline": False,
    },
    "critical_security_issues": {
        "label": "Critical/high security issues", "unit": "",
        "higher_is_better": False, "threshold": 0.5, "headline": False,
    },
    "dead_code_items": {
        "label": "Dead code items", "unit": "",
        "higher_is_better": False, "threshold": 2.5, "headline": False,
    },
    "critical_hotspots": {
        "label": "Critical hotspots", "unit": "",
        "higher_is_better": False, "threshold": 0.5, "headline": False,
    },
    "lines_of_code": {
        "label": "Lines of code", "unit": "",
        "higher_is_better": None, "threshold": 0.0, "headline": False,
    },
    "python_files": {
        "label": "Python files", "unit": "",
        "higher_is_better": None, "threshold": 0.0, "headline": False,
    },
}


def build_snapshot(report: Dict) -> Dict:
    """
    Reduce a full analysis report to the flat metric set we store per run.

    Keeping this deliberately small means a repository's whole history stays
    cheap to query and chart, and that the schema does not churn every time a
    detail is added to one of the analysis modules.
    """
    summary = report.get("summary", {})
    security = report.get("security", {})
    severity = security.get("severity_counts", {})
    history = report.get("history", {})

    return {
        "health_score": summary.get("health_score", {}).get("score", 0),
        "average_maintainability": summary.get("average_maintainability", 0.0),
        "average_complexity": summary.get("average_complexity", 0.0),
        "duplication_percentage": summary.get("duplication_percentage", 0.0),
        "security_score": security.get("security_score", 100.0),
        "type_hint_coverage": report.get("type_hints", {}).get("coverage", 0.0),
        "high_risk_functions": len(report.get("complexity", {}).get("high_risk_functions", [])),
        "critical_security_issues": severity.get("critical", 0) + severity.get("high", 0),
        "dead_code_items": report.get("dead_code", {}).get("total_items", 0),
        "critical_hotspots": history.get("summary", {}).get("critical_hotspots", 0),
        "lines_of_code": summary.get("lines_of_code", 0),
        "python_files": summary.get("python_files", 0),
    }


def _direction(key: str, delta: float) -> str:
    """Classify a change as an improvement, a regression, or noise."""
    spec = METRICS[key]
    if abs(delta) < spec["threshold"]:
        return "unchanged"
    if spec["higher_is_better"] is None:
        return "changed"
    improved = delta > 0 if spec["higher_is_better"] else delta < 0
    return "improved" if improved else "regressed"


def compare(previous: Optional[Dict], current: Dict) -> Dict:
    """
    Diff two metric snapshots.

    With no previous run there is nothing to compare against, so the result is
    marked `baseline` — the first analysis of a repository is a starting point,
    not an improvement or a regression.
    """
    if not previous:
        return {
            "available": False,
            "verdict": "baseline",
            "reason": "First analysis of this repository — nothing to compare against yet.",
            "changes": [],
            "regressions": [],
            "improvements": [],
        }

    changes: List[Dict] = []
    for key, spec in METRICS.items():
        before = previous.get(key)
        after = current.get(key)
        if before is None or after is None:
            continue

        delta = round(float(after) - float(before), 2)
        percent = round(delta / abs(float(before)) * 100, 1) if before else None

        changes.append({
            "metric": key,
            "label": spec["label"],
            "unit": spec["unit"],
            "before": before,
            "after": after,
            "delta": delta,
            "percent_change": percent,
            "direction": _direction(key, delta),
            "headline": spec["headline"],
        })

    regressions = [c for c in changes if c["direction"] == "regressed"]
    improvements = [c for c in changes if c["direction"] == "improved"]

    if regressions:
        verdict = "regressed"
    elif improvements:
        verdict = "improved"
    else:
        verdict = "unchanged"

    return {
        "available": True,
        "verdict": verdict,
        "reason": None,
        "changes": changes,
        "regressions": regressions,
        "improvements": improvements,
    }


def build_series(runs: Sequence[Dict]) -> Dict:
    """
    Turn stored runs into a chartable time series.

    `runs` must be ordered oldest-first and each entry needs `created_at`,
    `commit_sha` and a `metrics` snapshot.
    """
    points = [
        {
            "analysis_id": run["id"],
            "date": run["created_at"],
            "commit_sha": (run.get("commit_sha") or "")[:7] or None,
            **{key: run["metrics"].get(key) for key in METRICS},
        }
        for run in runs
        if run.get("metrics")
    ]

    if not points:
        return {"points": [], "run_count": 0, "metrics": [], "latest_comparison": None}

    latest_comparison = None
    if len(runs) >= 2:
        latest_comparison = compare(runs[-2].get("metrics"), runs[-1].get("metrics", {}))

    return {
        "points": points,
        "run_count": len(points),
        "metrics": [
            {"key": key, "label": spec["label"], "unit": spec["unit"],
             "higher_is_better": spec["higher_is_better"], "headline": spec["headline"]}
            for key, spec in METRICS.items()
        ],
        "latest_comparison": latest_comparison,
    }
