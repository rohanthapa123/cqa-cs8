# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A fullstack Python code analysis tool — a lightweight, Python-focused SonarQube. Users sign up, connect their GitHub account via OAuth, pick a repo, and get a report built around three core analysis modules: **Cyclomatic Complexity** (AST/McCabe via radon), **Duplicate Code Detection** (Winnowing fingerprinting over AST-normalized tokens), and **Maintainability** (Halstead metrics + Maintainability Index). A weighted 0–100 Overall Health Score summarizes the three. Bad-practices detection is a secondary auxiliary panel.

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
6. `AnalyzeResponse` has a `summary` (dashboard stats + health score) plus `complexity`, `duplication`, `maintainability`, and `bad_practices` sections; dashboard renders them across Overview / Complexity / Duplicates / Maintainability / Bad Practices tabs.

### Backend (`backend/`)

- `main.py` — app init, CORS middleware, router registration, DB table creation on startup (`lifespan`).
- `core/config.py` — `pydantic-settings` singleton; reads `.env`.
- `core/database.py` — SQLAlchemy engine + `SessionLocal` + `Base` + `get_db` dependency.
- `core/security.py` — bcrypt password hashing, JWT encode/decode (`python-jose`).
- `models/user.py` — `User` SQLAlchemy model (email, username, hashed_password, github_access_token, github_username).
- `schemas/auth.py` — `UserCreate`, `UserLogin`, `Token`, `UserResponse`.
- `schemas/analysis.py` — all analysis Pydantic models (summary/health, complexity, duplication, maintainability, bad practices).
- `services/auth.py` — user CRUD + `authenticate_user`.
- `services/analysis.py` — orchestrator: repo helpers (`clone_repo`, `is_python_project`, `collect_python_files`), `file_stats` (LOC/functions/classes), `compute_health_score` (weights: maintainability 0.40 / complexity 0.30 / duplication 0.30), and `analyze_repository` which fans out to the module below and assembles the response.
- `services/complexity.py` — cyclomatic complexity per function/file + repo average, high-risk list, distribution (radon `cc_visit`).
- `services/duplication.py` — Winnowing algorithm: AST token normalization → k-gram hashing (`K_GRAM`/`WINDOW`) → fingerprint selection → pairwise Jaccard similarity, duplicate line ranges, repo duplication %.
- `services/maintainability.py` — Halstead metrics from AST operators/operands + Maintainability Index (Coleman-Oman, normalized 0–100) with Excellent/Good/Fair/Poor ratings.
- `services/practices.py` — auxiliary AST bad-practices linter.
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
- `dashboard/page.tsx` — GitHub connect panel + searchable repo list + analysis results.
- `components/analysis/ReportViewer.tsx` — tabbed results (Overview / Complexity / Duplicates / Maintainability / Bad Practices) + Markdown report download.
- `components/analysis/SummaryPanel.tsx` — dashboard stat grid + Overall Health Score ring. `ComplexityTab`, `DuplicatesTab`, `MaintainabilityTab`, `PracticesTab` render each section.

## Next.js Version Warning

This project uses **Next.js 16.2.6**, which has breaking changes from earlier versions. Before modifying frontend code, consult `frontend/node_modules/next/dist/docs/` for current API conventions.

## Backend Dependencies

Install via `pip install -r backend/requirements.txt`.
