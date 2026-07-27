from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from backend.core.database import Base


class Analysis(Base):
    """A record of one repository analysis run, kept so admins can monitor activity."""

    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    repo_name = Column(String, nullable=False)
    repo_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="completed")  # completed | failed
    health_score = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
