# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A fullstack Python code analysis tool. Users sign up, connect their GitHub account via OAuth, pick a repo, and get a report.

**Three core modules** define the weighted 0–100 Overall Health Score: **Cyclomatic Complexity** (AST/McCabe via radon), **Duplicate Code Detection** (Winnowing fingerprinting over AST-normalized tokens), and **Maintainability** (Halstead metrics + Maintainability Index).

**Supporting modules** report alongside it:

- **Behavioural analysis** (`services/history.py`) — the differentiator. Reads the git commit log to derive churn, **hotspots** (churn × complexity), **change coupling** (files habitually committed together) and **bus factor** (knowledge concentration per file). Snapshot-based tools structurally cannot produce these.
- **Security** (`services/security.py`) — AST vulnerability patterns, Shannon-entropy secret detection, and dependency CVEs via the OSV.dev API.
- **Dead code** (`services/deadcode.py`) — whole-project reachability analysis.
- **Type hint coverage** (`services/typehints.py`) — PEP 484 annotation coverage per slot.
- **Trends** (`services/trends.py`) — every run stores a metric snapshot, so runs diff into regressions and chart over time.

Bad-practices detection remains a secondary auxiliary panel.

A GitHub webhook (`routers/webhooks.py`) runs the whole pipeline on pull requests, posting a sticky comment with the metric deltas and setting a commit status from a quality gate.

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

Copy `backend/.env.example` to `backend/.env` and fill in `JWT_SECRET`, `GITHUB_CLIENT_ID`, and `GITHUB_CLIENT_SECRET` before starting. Set `GITHUB_WEBHOOK_SECRET` to enable the pull-request endpoint — without it, `POST /webhooks/github` returns 503 rather than trusting unsigned payloads.

### Tests

```bash
./backend/.venv/bin/python -m pytest backend/tests -q
```

Note that `conftest.py` overrides `get_db` with SQLite, but the app's `lifespan` still touches the configured `DATABASE_URL` at startup, so the suite needs that database reachable.

## Architecture

### Data flow

1. User signs up / logs in → JWT stored in browser `localStorage`.
2. User connects GitHub via OAuth → backend stores `github_access_token` on the `User` row.
3. Dashboard fetches `GET /github/repos` → lists user's repos.
4. User selects repo → `POST /analyze` with `{ repo_url }`.
5. Backend clones (shallow to `settings.history_clone_depth`, **not** `depth=1` — behavioural analysis needs a commit log), checks Python project, runs all analyses, deletes clone.
6. The run's metric snapshot is persisted to the `analyses` table and diffed against the previous run for the same repo.
7. `AnalyzeResponse` carries `summary` (dashboard stats + health score) plus `complexity`, `duplication`, `maintainability`, `security`, `dead_code`, `type_hints`, `history`, `bad_practices` and `comparison`; the dashboard renders them across Overview / Hotspots / Trends / Security / Complexity / Duplicates / Maintainability / Dead Code / Type Hints / Bad Practices tabs.

### Pull-request flow

GitHub delivers a `pull_request` event to `POST /webhooks/github` → HMAC signature verified → commit status set to *pending* → analysis of `refs/pull/<n>/head` runs in a background task → result diffed against the repo's last run → sticky PR comment upserted → commit status resolved via the quality gate. `POST /webhooks/pull-request/check` runs the identical pipeline on demand, which is how you exercise it locally (webhooks cannot reach a laptop).

### Backend (`backend/`)

- `main.py` — app init, CORS middleware, router registration, DB table creation on startup (`lifespan`).
- `core/config.py` — `pydantic-settings` singleton; reads `.env`.
- `core/database.py` — SQLAlchemy engine + `SessionLocal` + `Base` + `get_db` dependency.
- `core/security.py` — bcrypt password hashing, JWT encode/decode (`python-jose`).
- `models/user.py` — `User` SQLAlchemy model (email, username, hashed_password, role, github_access_token, github_username).
- `models/analysis.py` — `Analysis` run record; `commit_sha`, `ref` and a `metrics` property backed by a JSON `metrics_json` column (Text, so it works on SQLite and Postgres alike). The snapshot is what makes trends possible.
- `schemas/auth.py` — `UserCreate`, `UserLogin`, `Token`, `UserResponse`.
- `schemas/analysis.py` — all analysis Pydantic models, numbered by section to match the services.
- `services/auth.py` — user CRUD + `authenticate_user`.
- `services/analysis.py` — orchestrator: repo helpers (`clone_repo` with optional `ref`, `head_commit`, `is_python_project`, `collect_python_files`), `file_stats` (LOC/functions/classes), `compute_health_score` (weights: maintainability 0.40 / complexity 0.30 / duplication 0.30), and `analyze_repository` which fans out to the modules below. AST modules share one `(rel_path, source)` list so each file is read once.
- `services/complexity.py` — cyclomatic complexity per function/file + repo average, high-risk list, distribution (radon `cc_visit`).
- `services/duplication.py` — Winnowing algorithm: AST token normalization → k-gram hashing (`K_GRAM`/`WINDOW`) → fingerprint selection → pairwise Jaccard similarity, duplicate line ranges, repo duplication %.
- `services/maintainability.py` — Halstead metrics from AST operators/operands + Maintainability Index (Coleman-Oman, normalized 0–100) with Excellent/Good/Fair/Poor ratings.
- `services/history.py` — behavioural analysis from `git log --numstat`. Exponentially time-decayed churn (`CHURN_HALF_LIFE_DAYS`), log-normalized churn × complexity hotspots, change coupling by conditional co-change probability (normalized by the *rarer* file so hot files don't couple to everything), and bus factor. Degrades to `available: False` on a shallow clone or non-git directory rather than failing the run.
- `services/security.py` — three passes: AST vulnerability rules, hardcoded-secret detection (name heuristics + provider token signatures + Shannon entropy, values redacted), and OSV.dev dependency advisories. Score decays exponentially (`SECURITY_SCORE_HALF_LIFE`) so bad repos stay distinguishable instead of all reading zero.
- `services/deadcode.py` — whole-project reachability. Self-references are subtracted so recursive-but-uncalled code is still caught; dunders, decorated functions, subclass methods, `__all__` exports, tests and `__init__.py` are conservatively treated as reachable, and every finding carries a confidence level.
- `services/typehints.py` — annotation coverage per *slot* (one per parameter plus one return), pooled repo-wide rather than averaged per file. `self`/`cls` excluded.
- `services/trends.py` — `METRICS` declares each tracked metric's direction and noise threshold; `build_snapshot`, `compare` (deltas + regression verdict) and `build_series` (chartable history).
- `services/practices.py` — auxiliary AST bad-practices linter.
- `routers/auth.py` — `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`; exports `get_current_user` dep used by other routers.
- `routers/github.py` — `GET /github/connect-url`, `GET /github/callback`, `GET /github/repos`, `POST /github/disconnect`.
- `routers/analyze.py` — `POST /analyze` (400 for non-Python repos, 500 otherwise) and `POST /analyze/export` (Markdown). Reads the diff baseline *before* inserting the new run.
- `routers/history.py` — `GET /analyses`, `GET /analyses/trend?repo_name=`, `GET /analyses/compare?base_id=&head_id=`. All scoped to the calling user.
- `routers/webhooks.py` — `POST /webhooks/github` (HMAC-verified) and `POST /webhooks/pull-request/check` (manual trigger). `evaluate_gate` blocks only on critical/high security findings or a health drop past `MAX_HEALTH_SCORE_DROP`; smaller regressions are reported but don't fail the build.

### Frontend (`frontend/app/`)

- `context/AuthContext.tsx` — `AuthProvider` + `useAuth` hook; JWT in `localStorage`, auto-hydrates via `/auth/me` on load.
- `api.ts` — Axios instance; request interceptor injects `Authorization: Bearer <token>`.
- `layout.tsx` — wraps tree in `AuthProvider` + `Navbar`.
- `components/Navbar.tsx` — client component; shows login/signup or user + dashboard + logout based on auth state.
- `page.tsx` — static landing page (hero, feature cards, how-it-works, CTA). Server component.
- `login/page.tsx`, `signup/page.tsx` — auth forms.
- `dashboard/page.tsx` — GitHub connect panel + searchable repo list + analysis results.
- `components/analysis/ReportViewer.tsx` — tabbed results + Markdown report download. Holds the `"use client"` boundary, so child tabs don't need their own directive.
- `components/analysis/SummaryPanel.tsx` — dashboard stat grid + Overall Health Score ring.
- Tab components: `ComplexityTab`, `DuplicatesTab`, `MaintainabilityTab`, `PracticesTab`, `SecurityTab`, `DeadCodeTab`, `TypeHintsTab`, `HotspotsTab` (churn × complexity SVG scatter + coupling + bus factor), `TrendsTab` (regression diff + metric history sparkline; the only tab that fetches, hitting `/analyses/trend`).

## Next.js Version Warning

This project uses **Next.js 16.2.6**, which has breaking changes from earlier versions. Before modifying frontend code, consult `frontend/node_modules/next/dist/docs/` for current API conventions.

## Backend Dependencies

Install via `pip install -r backend/requirements.txt`.
