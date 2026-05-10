import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.database import get_db
from backend.routers.auth import get_current_user
from backend.services.auth import get_user_by_id

router = APIRouter(prefix="/github", tags=["github"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


@router.get("/connect-url")
def get_connect_url(user=Depends(get_current_user)):
    url = (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope=repo+read:user"
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

    user.github_access_token = access_token
    user.github_username = github_profile.get("login")
    db.commit()

    return RedirectResponse(f"{settings.frontend_url}/dashboard?github=connected")


@router.get("/repos")
async def list_repos(user=Depends(get_current_user)):
    if not user.github_access_token:
        raise HTTPException(status_code=400, detail="GitHub account not connected")

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{GITHUB_API_URL}/user/repos",
            headers={
                "Authorization": f"Bearer {user.github_access_token}",
                "Accept": "application/json",
            },
            params={"sort": "updated", "per_page": 50, "type": "all"},
        )
        repos = res.json()

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
