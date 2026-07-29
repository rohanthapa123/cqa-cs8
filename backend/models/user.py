from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from backend.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user", server_default="user")

    # GitHub link. A GitHub App issues short-lived user tokens (~8h) plus a
    # rotating refresh token (~6 months), so both expiries are tracked and the
    # access token is renewed on demand — see `services/github_auth.py`.
    # OAuth App tokens never expire; for those the expiry columns stay NULL and
    # the refresh path is skipped entirely.
    github_access_token = Column(String, nullable=True)
    github_refresh_token = Column(String, nullable=True)
    github_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    github_refresh_expires_at = Column(DateTime(timezone=True), nullable=True)
    github_username = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
