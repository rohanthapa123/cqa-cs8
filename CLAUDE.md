# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A fullstack Python code analysis tool. Users sign up, connect their GitHub account via OAuth, pick a repo, and get a full report: cyclomatic complexity, duplicate file detection (TF-IDF cosine similarity), time complexity (AST Big-O), and bad practices.

## Commands

### Frontend (Next.js) — run from `frontend/`

```bash
npm run dev       # dev server on localhost:3000
npm run build     # production build
npm run lint      # ESLint
```

### Backend (FastAPI) — run from project root

```bash
uvicorn backend.main:app --reload   # dev server on localhost:8000
```

The backend is a Python package (`backend/__init__.py`), so it must be invoked from the project root with the dotted module path.

Copy `backend/.env.example` to `backend/.env` and fill in `JWT_SECRET`, `GITHUB_CLIENT_ID`, and `GITHUB_CLIENT_SECRET` before starting.

## Architecture

### Data flow

1. User signs up / logs in → JWT stored in browser `localStorage`.
2. User connects GitHub via OAuth → backend stores `github_access_token` on the `User` row.
3. Dashboard fetches `GET /github/repos` → lists user's repos.
4. User selects repo → `POST /analyze` with `{ repo_url }`.
5. Backend clones (shallow, `depth=1`), checks Python project, runs all analyses, deletes clone.
6. `AnalyzeResponse` has four sections; dashboard renders them in tabs.

### Backend (`backend/`)

- `main.py` — app init, CORS middleware, router registration, DB table creation on startup (`lifespan`).
- `core/config.py` — `pydantic-settings` singleton; reads `.env`.
- `core/database.py` — SQLAlchemy engine + `SessionLocal` + `Base` + `get_db` dependency.
- `core/security.py` — bcrypt password hashing, JWT encode/decode (`python-jose`).
- `models/user.py` — `User` SQLAlchemy model (email, username, hashed_password, github_access_token, github_username).
- `schemas/auth.py` — `UserCreate`, `UserLogin`, `Token`, `UserResponse`.
- `schemas/analysis.py` — all analysis Pydantic models.
- `services/auth.py` — user CRUD + `authenticate_user`.
- `services/analysis.py` — `is_python_project`, `clone_repo`, `compute_cyclomatic_complexity`, `compute_time_complexity`, `detect_bad_practices`, `compute_tfidf_cosine_similarity`, `analyze_repository`. Similarity pairs use `||` as internal key separator.
- `routers/auth.py` — `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`; exports `get_current_user` dep used by other routers.
- `routers/github.py` — `GET /github/connect-url` (returns OAuth URL JSON), `GET /github/callback` (exchanges code, stores token, redirects to frontend), `GET /github/repos`.
- `routers/analyze.py` — `POST /analyze`; raises `400` for non-Python repos, `500` for other errors.

### Frontend (`frontend/app/`)

- `context/AuthContext.tsx` — `AuthProvider` + `useAuth` hook; JWT in `localStorage`, auto-hydrates via `/auth/me` on load.
- `api.ts` — Axios instance; request interceptor injects `Authorization: Bearer <token>`.
- `layout.tsx` — wraps tree in `AuthProvider` + `Navbar`.
- `components/Navbar.tsx` — client component; shows login/signup or user + dashboard + logout based on auth state.
- `page.tsx` — static landing page (hero, feature cards, how-it-works, CTA). Server component.
- `login/page.tsx`, `signup/page.tsx` — auth forms.
- `dashboard/page.tsx` — GitHub connect panel + searchable repo list + analysis results with 4-tab display (cyclomatic / duplicates / time complexity / bad practices).

## Next.js Version Warning

This project uses **Next.js 16.2.6**, which has breaking changes from earlier versions. Before modifying frontend code, consult `frontend/node_modules/next/dist/docs/` for current API conventions.

## Backend Dependencies

Install via `pip install -r backend/requirements.txt`.
