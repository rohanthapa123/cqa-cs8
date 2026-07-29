"""
Command-line entrypoint, built for CI.

The webhook in `routers/webhooks.py` needs a running, publicly reachable
backend — which a GitHub Actions job is not. This runs the same analysis
against a checkout that already exists on disk and writes the results out as
files, so a workflow can post the comment itself using the token Actions
already hands it.

Typical use in a pull-request workflow:

    python -m backend.cli --path . --repo-name myrepo \\
        --baseline-ref origin/main \\
        --comment-out comment.md --gate-out gate.json

Analysing `--baseline-ref` as well makes the diff self-contained: the workflow
does not need anywhere to persist the previous run's metrics, because it
measures the base branch in the same job.

Exit codes:
    0  analysis completed (quality gate passed, or --no-fail-on-gate given)
    1  quality gate failed
    2  analysis could not run at all
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, Optional

from backend.services import trends
from backend.services.analysis import analyze_path
from backend.services.pr_report import evaluate_gate, render_comment


def _run_git(args, cwd: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def analyze_baseline(path: str, repo_name: str, baseline_ref: str) -> Optional[Dict]:
    """
    Measure the base branch so the report can show what this PR changed.

    The base is checked out into a **separate git worktree** in a temporary
    directory rather than being checked out over the top of `path`. This is not
    a stylistic choice: `git checkout` on the working tree would discard any
    uncommitted modifications, which is data loss on a developer's machine even
    though CI checkouts are always clean.

    Best-effort throughout — a shallow clone lacking the base commit, or a
    worktree that cannot be created, degrades the report to "no comparison"
    rather than failing the run.
    """
    if _run_git(["rev-parse", "--verify", f"{baseline_ref}^{{commit}}"], path) is None:
        print(f"  baseline ref '{baseline_ref}' not found in this checkout — skipping comparison")
        return None

    worktree = tempfile.mkdtemp(prefix="codescope_baseline_")
    try:
        # --detach avoids claiming the branch, so the same ref can stay checked
        # out in the main worktree.
        if _run_git(["worktree", "add", "--detach", "--quiet", worktree, baseline_ref], path) is None:
            print(f"  could not create a worktree for '{baseline_ref}' — skipping comparison")
            return None

        print(f"  analysing baseline {baseline_ref}...")
        return trends.build_snapshot(analyze_path(worktree, repo_name))
    except Exception as e:
        print(f"  baseline analysis failed ({e}) — skipping comparison")
        return None
    finally:
        _run_git(["worktree", "remove", "--force", worktree], path)
        shutil.rmtree(worktree, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description="Run a CodeScope analysis over a local checkout.",
    )
    parser.add_argument("--path", default=".", help="Directory to analyse (default: .)")
    parser.add_argument("--repo-name", help="Name for the report (default: the directory name)")
    parser.add_argument(
        "--baseline-ref",
        help="Git ref to analyse for comparison, e.g. origin/main. Omit to skip the diff.",
    )
    parser.add_argument("--comment-out", help="Write the Markdown PR comment here")
    parser.add_argument("--report-out", help="Write the full analysis JSON here")
    parser.add_argument("--gate-out", help="Write the quality-gate verdict JSON here")
    parser.add_argument(
        "--no-fail-on-gate", action="store_true",
        help="Always exit 0, even when the quality gate fails",
    )
    args = parser.parse_args()

    path = os.path.abspath(args.path)
    repo_name = args.repo_name or os.path.basename(path.rstrip(os.sep)) or "repository"

    baseline_metrics = None
    if args.baseline_ref:
        baseline_metrics = analyze_baseline(path, repo_name, args.baseline_ref)

    print(f"  analysing {repo_name}...")
    try:
        report = analyze_path(path, repo_name)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: analysis failed: {e}", file=sys.stderr)
        return 2

    snapshot = trends.build_snapshot(report)
    comparison = trends.compare(baseline_metrics, snapshot)
    state, description = evaluate_gate(snapshot, comparison)

    summary = report["summary"]
    health = summary["health_score"]
    print()
    print(f"  health score     {health['score']}/100 (grade {health['grade']})")
    print(f"  security score   {summary['security_score']}/100")
    print(f"  complexity       {summary['average_complexity']} avg")
    print(f"  duplication      {summary['duplication_percentage']}%")
    print(f"  type coverage    {summary['type_hint_coverage']}%")
    print(f"  dead code        {summary['dead_code_items']} items")
    print(f"  quality gate     {state.upper()} — {description}")
    print()

    if args.comment_out:
        with open(args.comment_out, "w", encoding="utf-8") as f:
            f.write(render_comment(report, snapshot, comparison, state, description))
        print(f"  wrote {args.comment_out}")

    if args.report_out:
        with open(args.report_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  wrote {args.report_out}")

    if args.gate_out:
        with open(args.gate_out, "w", encoding="utf-8") as f:
            json.dump({
                "state": state,
                "description": description,
                "snapshot": snapshot,
                "verdict": comparison["verdict"],
                "regressions": [c["label"] for c in comparison.get("regressions", [])],
            }, f, indent=2)
        print(f"  wrote {args.gate_out}")

    # Write the headline into the Actions run summary when available.
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as f:
            f.write(f"### CodeScope\n\n**Health {health['score']}/100 "
                    f"(grade {health['grade']})** — quality gate {state}\n\n{description}\n")

    if state == "failure" and not args.no_fail_on_gate:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
