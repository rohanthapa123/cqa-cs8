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
from backend.routers.history import router as history_router
from backend.routers.webhooks import router as webhooks_router

# Columns added after the initial release. SQLite and Postgres both accept
# `ALTER TABLE ... ADD COLUMN` for nullable columns, which is all we need.
_ADDED_COLUMNS = {
    "users": [
        ("role", "VARCHAR NOT NULL DEFAULT 'user'"),
        ("github_refresh_token", "VARCHAR"),
        ("github_token_expires_at", "TIMESTAMP"),
        ("github_refresh_expires_at", "TIMESTAMP"),
    ],
    "analyses": [
        ("commit_sha", "VARCHAR"),
        ("ref", "VARCHAR"),
        ("metrics_json", "TEXT"),
    ],
}


def _ensure_schema() -> None:
    """
    Bring pre-existing tables up to date with the current models.

    `create_all` only creates missing *tables*, so a database created before
    admin roles or trend snapshots existed would silently lack those columns.
    """
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    pending: list[str] = []
    for table, columns in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {c["name"] for c in insp.get_columns(table)}
        pending += [
            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
            for name, definition in columns
            if name not in present
        ]

    if not pending:
        return

    # One connection and one transaction for the whole migration, so a partial
    # apply cannot leave the schema half-upgraded.
    with engine.begin() as conn:
        for statement in pending:
            conn.execute(text(statement))


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
app.include_router(history_router)
app.include_router(webhooks_router)
app.include_router(admin_router)
