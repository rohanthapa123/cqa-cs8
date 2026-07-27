from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.models.analysis import Analysis
from backend.models.user import User
from backend.routers.auth import get_current_user
from backend.schemas.admin import AdminAnalysisView, AdminStats, AdminUserView

router = APIRouter(prefix="/admin", tags=["admin"])


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Allow only admin users; other authenticated users get 403."""
    if getattr(user, "role", "user") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/stats", response_model=AdminStats)
def admin_stats(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    admin_users = db.query(User).filter(User.role == "admin").count()
    github_connected = db.query(User).filter(User.github_username.isnot(None)).count()
    total_analyses = db.query(Analysis).count()
    completed = db.query(Analysis).filter(Analysis.status == "completed").count()
    failed = db.query(Analysis).filter(Analysis.status == "failed").count()
    return AdminStats(
        total_users=total_users,
        admin_users=admin_users,
        github_connected=github_connected,
        total_analyses=total_analyses,
        completed_analyses=completed,
        failed_analyses=failed,
    )


@router.get("/users", response_model=list[AdminUserView])
def list_users(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.get("/analyses", response_model=list[AdminAnalysisView])
def list_analyses(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(Analysis, User.username)
        .join(User, User.id == Analysis.user_id)
        .order_by(Analysis.id.desc())
        .limit(100)
        .all()
    )
    return [
        AdminAnalysisView(
            id=a.id,
            user_id=a.user_id,
            username=username,
            repo_name=a.repo_name,
            repo_url=a.repo_url,
            status=a.status,
            health_score=a.health_score,
            created_at=a.created_at,
        )
        for a, username in rows
    ]


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete another admin")
    # remove the user's analyses first (portable across databases)
    db.query(Analysis).filter(Analysis.user_id == user_id).delete()
    db.delete(target)
    db.commit()
    return {"status": "deleted", "id": user_id}
