"""
GitHub token lifecycle.

The credentials this project is configured with belong to a **GitHub App**,
which issues *user-to-server* tokens (`ghu_...`). Unlike OAuth App tokens
(`gho_...`), these expire after about eight hours and arrive with a rotating
refresh token that is valid for roughly six months. Storing only the access
token means every link silently dies overnight, which is what
`ensure_fresh_token` exists to prevent.

Both app types are supported. When the token response carries no `expires_in` —
the OAuth App case — the expiry columns stay NULL and refreshing is skipped, so
the same code works whichever kind of app the deployment is pointed at.

Refresh tokens are single-use: exchanging one returns a *new* refresh token and
invalidates the old one, so the response must always be persisted in full or the
link is lost.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import httpx
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.user import User

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"

# Refresh this long before actual expiry, so a token cannot die mid-analysis.
# A repository analysis can run for minutes; a token with four minutes left
# would expire underneath it.
REFRESH_MARGIN = timedelta(minutes=10)

HTTP_TIMEOUT = 20.0


class GitHubAuthError(Exception):
    """The GitHub link cannot be used and the user has to reconnect."""


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
    Normalise a stored timestamp to an aware UTC datetime.

    SQLite drops timezone information, so a value written as aware comes back
    naive. Comparing that against an aware `now()` raises, hence this guard.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------

def store_token(db: Session, user: User, token_data: Dict,
                github_username: Optional[str] = None) -> None:
    """
    Persist a token response from GitHub.

    Handles both app types: `expires_in` and `refresh_token` are present for a
    GitHub App and absent for an OAuth App.
    """
    now = _utcnow()

    user.github_access_token = token_data["access_token"]

    expires_in = token_data.get("expires_in")
    user.github_token_expires_at = (
        now + timedelta(seconds=int(expires_in)) if expires_in else None
    )

    # Only overwrite the refresh token when GitHub sends one — a response
    # without it must not wipe a still-valid token we already hold.
    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        user.github_refresh_token = refresh_token
        refresh_expires_in = token_data.get("refresh_token_expires_in")
        user.github_refresh_expires_at = (
            now + timedelta(seconds=int(refresh_expires_in)) if refresh_expires_in else None
        )

    if github_username:
        user.github_username = github_username

    db.commit()


def clear_token(db: Session, user: User) -> None:
    """Unlink GitHub locally, leaving no partial state behind."""
    user.github_access_token = None
    user.github_refresh_token = None
    user.github_token_expires_at = None
    user.github_refresh_expires_at = None
    user.github_username = None
    db.commit()


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------

def is_expired(user: User, margin: timedelta = REFRESH_MARGIN) -> bool:
    """True when the access token is gone, or close enough to expiry to renew."""
    expires_at = _as_utc(user.github_token_expires_at)
    if expires_at is None:
        return False  # OAuth App token: no expiry to worry about
    return _utcnow() + margin >= expires_at


def refresh_access_token(db: Session, user: User) -> str:
    """
    Exchange the refresh token for a new access token.

    Raises `GitHubAuthError` when the link is beyond saving — no refresh token,
    a refresh token past its own six-month expiry, or a rejection from GitHub —
    so callers can tell the user to reconnect rather than retrying forever.
    """
    if not user.github_refresh_token:
        raise GitHubAuthError(
            "This GitHub link predates automatic token refresh. "
            "Please disconnect and reconnect your GitHub account."
        )

    refresh_expires_at = _as_utc(user.github_refresh_expires_at)
    if refresh_expires_at and _utcnow() >= refresh_expires_at:
        raise GitHubAuthError(
            "Your GitHub authorization has expired. Please reconnect your GitHub account."
        )

    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            response = client.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": user.github_refresh_token,
                },
                headers={"Accept": "application/json"},
            )
            payload = response.json()
    except Exception as e:
        raise GitHubAuthError(f"Could not reach GitHub to refresh the token: {e}")

    # GitHub signals refresh failures with a 200 and an `error` key.
    if "access_token" not in payload:
        reason = payload.get("error_description") or payload.get("error") or "unknown error"
        raise GitHubAuthError(
            f"GitHub refused to refresh the token ({reason}). "
            "Please disconnect and reconnect your GitHub account."
        )

    store_token(db, user, payload)
    return user.github_access_token


def ensure_fresh_token(db: Session, user: User) -> str:
    """
    Return a usable access token, refreshing first if it is close to expiry.

    Every GitHub API call should obtain its token through this rather than
    reading `user.github_access_token` directly.
    """
    if not user.github_access_token:
        raise GitHubAuthError("GitHub account not connected")

    if is_expired(user):
        return refresh_access_token(db, user)

    return user.github_access_token


# ---------------------------------------------------------------------------
# revocation
# ---------------------------------------------------------------------------

def revoke_token(access_token: str) -> bool:
    """
    Ask GitHub to invalidate a user access token.

    `DELETE /applications/{client_id}/token` is the right endpoint for both app
    types. Note that for a GitHub App this revokes the *token* only — the app's
    installation and the user's authorization of it both survive, which is why
    reconnecting does not re-prompt unless the consent screen is forced.
    """
    if not access_token:
        return False
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            response = client.request(
                "DELETE",
                f"{GITHUB_API_URL}/applications/{settings.github_client_id}/token",
                auth=(settings.github_client_id, settings.github_client_secret),
                json={"access_token": access_token},
                headers={"Accept": "application/vnd.github+json"},
            )
        return response.status_code in (204, 404)
    except Exception:
        return False
