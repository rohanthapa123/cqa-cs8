"""
Tests for GitHub token lifecycle.

The credentials this project uses belong to a GitHub App, whose user tokens
(`ghu_...`) expire after ~8 hours. These cover the refresh path that keeps a
link alive, and the OAuth App path where there is nothing to refresh.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.models.user import User
from backend.services import github_auth
from backend.services.github_auth import GitHubAuthError
from backend.tests.conftest import TestingSessionLocal


def utcnow():
    return datetime.now(timezone.utc)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def user(db):
    """
    A throwaway user, removed afterwards.

    `store_token` commits, so the session rollback alone would not undo it —
    and a leaked row carrying a `github_username` gets picked up by the
    webhook's `resolve_actor` lookup in an unrelated test file.
    """
    import uuid
    unique = uuid.uuid4().hex[:8]
    record = User(
        email=f"gh-{unique}@example.com",
        username=f"gh{unique}",
        hashed_password="x",
    )
    db.add(record)
    db.commit()

    yield record

    db.delete(record)
    db.commit()


# A GitHub App token response; an OAuth App omits every expiry field.
GITHUB_APP_RESPONSE = {
    "access_token": "ghu_newaccess",
    "expires_in": 28800,
    "refresh_token": "ghr_newrefresh",
    "refresh_token_expires_in": 15811200,
    "token_type": "bearer",
}

OAUTH_APP_RESPONSE = {"access_token": "gho_static", "token_type": "bearer", "scope": "repo"}


# ---------------------------------------------------------------------------
# storing tokens
# ---------------------------------------------------------------------------

def test_stores_github_app_token_with_both_expiries(db, user):
    github_auth.store_token(db, user, GITHUB_APP_RESPONSE, "gh-fixture-user")

    assert user.github_access_token == "ghu_newaccess"
    assert user.github_refresh_token == "ghr_newrefresh"
    assert user.github_username == "gh-fixture-user"
    assert github_auth._as_utc(user.github_token_expires_at) > utcnow() + timedelta(hours=7)
    assert github_auth._as_utc(user.github_refresh_expires_at) > utcnow() + timedelta(days=180)


def test_oauth_app_token_has_no_expiry(db, user):
    github_auth.store_token(db, user, OAUTH_APP_RESPONSE, "gh-fixture-user")

    assert user.github_access_token == "gho_static"
    assert user.github_token_expires_at is None
    assert user.github_refresh_token is None


def test_a_response_without_a_refresh_token_keeps_the_existing_one(db, user):
    github_auth.store_token(db, user, GITHUB_APP_RESPONSE)
    github_auth.store_token(db, user, {"access_token": "ghu_second", "expires_in": 28800})

    assert user.github_access_token == "ghu_second"
    assert user.github_refresh_token == "ghr_newrefresh"  # not wiped


def test_clear_removes_every_field(db, user):
    github_auth.store_token(db, user, GITHUB_APP_RESPONSE, "gh-fixture-user")
    github_auth.clear_token(db, user)

    assert user.github_access_token is None
    assert user.github_refresh_token is None
    assert user.github_token_expires_at is None
    assert user.github_refresh_expires_at is None
    assert user.github_username is None


# ---------------------------------------------------------------------------
# expiry detection
# ---------------------------------------------------------------------------

def test_token_with_hours_left_is_not_expired(db, user):
    user.github_token_expires_at = utcnow() + timedelta(hours=5)
    assert github_auth.is_expired(user) is False


def test_token_inside_the_refresh_margin_counts_as_expired(db, user):
    # Refreshed early on purpose: an analysis can run for minutes, and a token
    # with four minutes left would die underneath it.
    user.github_token_expires_at = utcnow() + timedelta(minutes=4)
    assert github_auth.is_expired(user) is True


def test_already_expired_token_is_expired(db, user):
    user.github_token_expires_at = utcnow() - timedelta(hours=1)
    assert github_auth.is_expired(user) is True


def test_oauth_app_token_never_counts_as_expired(db, user):
    user.github_token_expires_at = None
    assert github_auth.is_expired(user) is False


def test_naive_timestamps_are_treated_as_utc(db, user):
    # SQLite drops tzinfo; comparing naive against aware would raise TypeError.
    user.github_token_expires_at = (utcnow() + timedelta(hours=5)).replace(tzinfo=None)
    assert github_auth.is_expired(user) is False


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for httpx.Client, capturing the form data GitHub would receive."""

    def __init__(self, payload, recorder=None):
        self._payload = payload
        self._recorder = recorder

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, data=None, headers=None):
        if self._recorder is not None:
            self._recorder.update({"url": url, "data": data})
        return FakeResponse(self._payload)


def patch_client(monkeypatch, payload, recorder=None):
    monkeypatch.setattr(
        github_auth.httpx, "Client",
        lambda *a, **kw: FakeClient(payload, recorder),
    )


def test_refresh_exchanges_the_refresh_token(db, user, monkeypatch):
    user.github_access_token = "ghu_old"
    user.github_refresh_token = "ghr_old"
    user.github_token_expires_at = utcnow() - timedelta(minutes=1)

    sent = {}
    patch_client(monkeypatch, GITHUB_APP_RESPONSE, sent)

    token = github_auth.refresh_access_token(db, user)

    assert token == "ghu_newaccess"
    assert sent["data"]["grant_type"] == "refresh_token"
    assert sent["data"]["refresh_token"] == "ghr_old"


def test_refresh_stores_the_rotated_refresh_token(db, user, monkeypatch):
    # GitHub invalidates the old refresh token on use, so the new one must be
    # persisted or the link is lost on the following refresh.
    user.github_refresh_token = "ghr_old"
    patch_client(monkeypatch, GITHUB_APP_RESPONSE)

    github_auth.refresh_access_token(db, user)

    assert user.github_refresh_token == "ghr_newrefresh"


def test_refresh_without_a_refresh_token_asks_the_user_to_reconnect(db, user):
    user.github_access_token = "ghu_old"
    user.github_refresh_token = None

    with pytest.raises(GitHubAuthError, match="reconnect"):
        github_auth.refresh_access_token(db, user)


def test_refresh_past_the_six_month_window_asks_the_user_to_reconnect(db, user):
    user.github_refresh_token = "ghr_old"
    user.github_refresh_expires_at = utcnow() - timedelta(days=1)

    with pytest.raises(GitHubAuthError, match="expired"):
        github_auth.refresh_access_token(db, user)


def test_github_rejecting_the_refresh_raises(db, user, monkeypatch):
    # GitHub reports refresh failures with HTTP 200 and an `error` key.
    user.github_refresh_token = "ghr_stale"
    patch_client(monkeypatch, {"error": "bad_refresh_token",
                               "error_description": "The refresh token is incorrect or expired."})

    with pytest.raises(GitHubAuthError, match="incorrect or expired"):
        github_auth.refresh_access_token(db, user)


def test_network_failure_during_refresh_raises(db, user, monkeypatch):
    user.github_refresh_token = "ghr_old"

    def explode(*a, **kw):
        raise OSError("connection reset")

    monkeypatch.setattr(github_auth.httpx, "Client", explode)

    with pytest.raises(GitHubAuthError, match="Could not reach GitHub"):
        github_auth.refresh_access_token(db, user)


# ---------------------------------------------------------------------------
# ensure_fresh_token
# ---------------------------------------------------------------------------

def test_valid_token_is_returned_untouched(db, user, monkeypatch):
    user.github_access_token = "ghu_valid"
    user.github_token_expires_at = utcnow() + timedelta(hours=5)

    def fail(*a, **kw):
        raise AssertionError("must not refresh a healthy token")

    monkeypatch.setattr(github_auth, "refresh_access_token", fail)

    assert github_auth.ensure_fresh_token(db, user) == "ghu_valid"


def test_expiring_token_is_refreshed_transparently(db, user, monkeypatch):
    user.github_access_token = "ghu_old"
    user.github_refresh_token = "ghr_old"
    user.github_token_expires_at = utcnow() + timedelta(minutes=2)
    patch_client(monkeypatch, GITHUB_APP_RESPONSE)

    assert github_auth.ensure_fresh_token(db, user) == "ghu_newaccess"


def test_oauth_app_token_is_returned_without_refreshing(db, user, monkeypatch):
    user.github_access_token = "gho_static"
    user.github_token_expires_at = None

    def fail(*a, **kw):
        raise AssertionError("OAuth App tokens have nothing to refresh")

    monkeypatch.setattr(github_auth, "refresh_access_token", fail)

    assert github_auth.ensure_fresh_token(db, user) == "gho_static"


def test_unconnected_account_raises(db, user):
    user.github_access_token = None
    with pytest.raises(GitHubAuthError, match="not connected"):
        github_auth.ensure_fresh_token(db, user)


# ---------------------------------------------------------------------------
# connect URL
# ---------------------------------------------------------------------------

def test_connect_url_forces_the_account_chooser(client):
    unique = "picker"
    signup = client.post("/auth/signup", json={
        "email": f"{unique}@example.com", "username": unique, "password": "correct-horse-battery",
    })
    token = signup.json()["access_token"]

    url = client.get("/github/connect-url", headers={"Authorization": f"Bearer {token}"}).json()["url"]

    # Without this GitHub silently re-links the same account instead of asking.
    assert "prompt=select_account" in url
