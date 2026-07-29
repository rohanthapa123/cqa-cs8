import json
from typing import Dict, Optional

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from backend.core.database import Base


class Analysis(Base):
    """
    A record of one repository analysis run.

    Beyond letting admins monitor activity, each row stores a flat snapshot of
    the run's headline metrics (see `services/trends.py`). That snapshot is
    what makes trend charts and regression diffs possible — without it every
    analysis would be an isolated point with nothing to compare against.

    The snapshot is kept as a JSON string rather than a JSON column so the same
    code works on both SQLite and PostgreSQL.
    """

    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    repo_name = Column(String, nullable=False, index=True)
    repo_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="completed")  # completed | failed
    health_score = Column(Integer, nullable=True)
    commit_sha = Column(String, nullable=True)
    ref = Column(String, nullable=True)  # branch or PR ref this run analysed
    metrics_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def metrics(self) -> Optional[Dict]:
        """The stored metric snapshot, or None if this run predates snapshots."""
        if not self.metrics_json:
            return None
        try:
            return json.loads(self.metrics_json)
        except (ValueError, TypeError):
            return None

    @metrics.setter
    def metrics(self, value: Optional[Dict]) -> None:
        self.metrics_json = json.dumps(value) if value else None
