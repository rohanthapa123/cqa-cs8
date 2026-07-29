"""
Analysis history endpoints.

Every run persists a metric snapshot, which turns the stored `analyses` table
into a time series per repository. These endpoints expose it: a list of past
runs, a chartable trend for one repository, and an explicit diff between any
two runs the caller owns.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.analysis import Analysis
from backend.routers.auth import get_current_user
from backend.schemas.analysis import AnalysisRun, ComparisonReport, TrendSeries
from backend.services import trends

router = APIRouter(prefix="/analyses", tags=["history"])

MAX_TREND_POINTS = 50


def _serialize(run: Analysis) -> AnalysisRun:
    return AnalysisRun(
        id=run.id,
        repo_name=run.repo_name,
        repo_url=run.repo_url,
        status=run.status,
        health_score=run.health_score,
        commit_sha=run.commit_sha,
        ref=run.ref,
        created_at=run.created_at.isoformat() if run.created_at else None,
    )


def _owned_run(db: Session, run_id: int, user_id: int) -> Analysis:
    run = db.query(Analysis).filter(Analysis.id == run_id, Analysis.user_id == user_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Analysis {run_id} not found")
    return run


@router.get("", response_model=List[AnalysisRun])
def list_runs(
    repo_name: Optional[str] = Query(None, description="Filter to a single repository"),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The caller's past analysis runs, newest first."""
    query = db.query(Analysis).filter(Analysis.user_id == user.id)
    if repo_name:
        query = query.filter(Analysis.repo_name == repo_name)
    runs = query.order_by(Analysis.created_at.desc(), Analysis.id.desc()).limit(limit).all()
    return [_serialize(run) for run in runs]


@router.get("/trend", response_model=TrendSeries)
def repository_trend(
    repo_name: str = Query(..., description="Repository to chart"),
    limit: int = Query(MAX_TREND_POINTS, ge=2, le=200),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Metric history for one repository, oldest point first.

    Only successful runs that carry a snapshot are included — failed runs have
    no metrics and would punch holes in the chart.
    """
    runs = (
        db.query(Analysis)
        .filter(
            Analysis.user_id == user.id,
            Analysis.repo_name == repo_name,
            Analysis.status == "completed",
            Analysis.metrics_json.isnot(None),
        )
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(limit)
        .all()
    )
    runs.reverse()  # chart chronologically

    series = trends.build_series([
        {
            "id": run.id,
            "created_at": run.created_at.isoformat() if run.created_at else "",
            "commit_sha": run.commit_sha,
            "metrics": run.metrics,
        }
        for run in runs
    ])

    return TrendSeries(repo_name=repo_name, **series)


@router.get("/compare", response_model=ComparisonReport)
def compare_runs(
    base_id: int = Query(..., description="The earlier run"),
    head_id: int = Query(..., description="The later run"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Diff two stored runs into per-metric deltas and a regression verdict."""
    base = _owned_run(db, base_id, user.id)
    head = _owned_run(db, head_id, user.id)

    if head.metrics is None:
        raise HTTPException(status_code=400, detail=f"Analysis {head_id} has no stored metrics")

    return trends.compare(base.metrics, head.metrics)
