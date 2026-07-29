import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.database import get_db
from backend.routers.auth import get_current_user
from backend.services import github_auth
from backend.services.auth import get_user_by_id

router = APIRouter(prefix="/github", tags=["github"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


@router.get("/connect-url")
def get_connect_url(user=Depends(get_current_user)):
    """
    Build the GitHub authorization URL.

    `prompt=select_account` forces the account chooser. Without it GitHub sees
    an existing authorization and bounces straight back, so a user who wanted to
    link a *different* account would silently get the same one again.

    `scope` only means something to an OAuth App — a GitHub App ignores it and
    uses the permissions declared on the app itself.
    """
    url = (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope=repo+read:user"
        f"&prompt=select_account"
        f"&state={user.id}"
    )
    return {"url": url}


@router.get("/callback")
async def github_callback(code: str, state: str, db: Session = Depends(get_db)):
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_res.json()

    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(f"{settings.frontend_url}/dashboard?error=github_auth_failed")

    async with httpx.AsyncClient() as client:
        user_res = await client.get(
            f"{GITHUB_API_URL}/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        github_profile = user_res.json()

    user = get_user_by_id(db, int(state))
    if not user:
        return RedirectResponse(f"{settings.frontend_url}/dashboard?error=user_not_found")

    # Stores the refresh token and both expiries alongside the access token —
    # a GitHub App token is dead in ~8 hours without them.
    github_auth.store_token(db, user, token_data, github_profile.get("login"))

    return RedirectResponse(f"{settings.frontend_url}/dashboard?github=connected")


@router.get("/repos")
async def list_repos(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.github_access_token:
        raise HTTPException(status_code=400, detail="GitHub account not connected")

    try:
        token = github_auth.ensure_fresh_token(db, user)
    except github_auth.GitHubAuthError as e:
        # 400, not 401 — a 401 here would trip the frontend's global
        # "session expired -> log out" handler and dump the user at /login.
        raise HTTPException(status_code=400, detail=str(e))

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{GITHUB_API_URL}/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            params={"sort": "updated", "per_page": 100, "affiliation": "owner,collaborator,organization_member"},
        )

    if res.status_code == 401:
        raise HTTPException(
            status_code=400,
            detail="GitHub authorization was revoked. Please disconnect and reconnect your GitHub account.",
        )
    if res.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API error ({res.status_code}): {res.text[:200]}")

    repos = res.json()
    if not isinstance(repos, list):
        raise HTTPException(status_code=502, detail=f"Unexpected GitHub response: {str(repos)[:200]}")

    return [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "html_url": r["html_url"],
            "clone_url": r["clone_url"],
            "description": r.get("description"),
            "language": r.get("language"),
            "updated_at": r.get("updated_at"),
            "private": r["private"],
            "stargazers_count": r.get("stargazers_count", 0),
        }
        for r in repos
        if isinstance(r, dict) and "name" in r
    ]


@router.post("/disconnect")
async def disconnect_github(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Unlink the connected GitHub account so a different one can be linked.

    The token is revoked on GitHub's side too, but note what that does *not*
    do for a GitHub App: the app stays installed and the user's authorization
    of it survives, so GitHub will not show the consent screen again. The
    account chooser is forced by `prompt=select_account` on the connect URL
    instead. To remove the app entirely the user has to do it from
    GitHub Settings → Applications.
    """
    revoked = github_auth.revoke_token(user.github_access_token)
    github_auth.clear_token(db, user)
    return {"status": "disconnected", "token_revoked": revoked}
