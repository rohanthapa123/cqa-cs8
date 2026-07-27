from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AdminUserView(BaseModel):
    id: int
    email: str
    username: str
    role: str
    github_username: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AdminAnalysisView(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    repo_name: str
    repo_url: str
    status: str
    health_score: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AdminStats(BaseModel):
    total_users: int
    admin_users: int
    github_connected: int
    total_analyses: int
    completed_analyses: int
    failed_analyses: int
