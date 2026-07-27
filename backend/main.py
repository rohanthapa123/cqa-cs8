from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from backend.core.config import settings
from backend.core.database import Base, SessionLocal, engine
from backend.models.analysis import Analysis  # noqa: F401 (register table)
from backend.models.user import User
from backend.routers.admin import router as admin_router
from backend.routers.analyze import router as analyze_router
from backend.routers.auth import router as auth_router
from backend.routers.github import router as github_router


def _ensure_schema() -> None:
    """Add the `role` column to pre-existing `users` tables that predate admin support."""
    insp = inspect(engine)
    if "users" in insp.get_table_names():
        columns = {c["name"] for c in insp.get_columns("users")}
        if "role" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR NOT NULL DEFAULT 'user'"))


def _promote_admins() -> None:
    """Promote any emails listed in ADMIN_EMAILS to the admin role."""
    emails = [e.strip() for e in settings.admin_emails.split(",") if e.strip()]
    if not emails:
        return
    db = SessionLocal()
    try:
        for email in emails:
            user = db.query(User).filter(User.email == email).first()
            if user and user.role != "admin":
                user.role = "admin"
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
    _promote_admins()
    yield


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=settings.allow_credentials,
    allow_methods=settings.allow_methods,
    allow_headers=settings.allow_headers,
)

app.include_router(auth_router)
app.include_router(github_router)
app.include_router(analyze_router)
app.include_router(admin_router)
