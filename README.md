# CodeScope

A fullstack Python code-analysis tool. Sign up, connect your GitHub account via OAuth, pick a repository, and get a structured report covering cyclomatic complexity, duplicate-file detection, estimated time complexity, bad-practice findings, and test coverage — all rendered in a tabbed dashboard and exportable as Markdown.

## What it is

CodeScope is a web app that turns a GitHub repository into a readable health report for its Python code. Instead of installing and wiring up a handful of separate command-line linters and complexity tools, you log in, point CodeScope at one of your repos, and it runs the analyses for you and presents the results in one place. Everything happens on demand — the repo is cloned, measured, and immediately deleted, so nothing is stored on disk after a run.

## Who it's for and how it helps

It's aimed at developers, reviewers, and teams who want a quick, objective read on a Python codebase without setting up tooling per project.

- **Spot risky code fast** — high cyclomatic-complexity functions and nested-loop hotspots surface immediately, so you know where bugs and slowdowns are most likely to live.
- **Find copy-paste and duplication** — TF-IDF similarity highlights files that are near-duplicates and ripe for refactoring.
- **Catch common mistakes** — an AST scan flags bare excepts, mutable default arguments, wildcard imports, `eval`/`exec`, and other smells before they reach review.
- **Gauge test discipline** — a glance shows whether a repo ships tests and how many.
- **Share the results** — export the whole report as a Markdown file to drop into a PR, a wiki, or a ticket.

## Features

- **GitHub OAuth integration** — connect once and browse all your repositories; analysis currently clones over HTTPS, so public repos work out of the box (private-repo cloning is on the roadmap).
- **Five analyses in one report** — cyclomatic complexity, duplicate detection, time-complexity estimation, bad-practice detection, and test-coverage detection (see the table below).
- **Tabbed dashboard** — each analysis gets its own tab with per-file, per-function breakdowns.
- **Markdown export** — download a formatted report with summary metrics and severity flags.
- **JWT authentication** — email/password accounts with bcrypt-hashed passwords and token-based sessions.
- **Ephemeral, safe clones** — repos are shallow-cloned (`depth=1`), analyzed, and deleted; non-Python repos are rejected early.

## How it works

1. You sign up or log in. A JWT is issued and stored in the browser's `localStorage`.
2. You connect GitHub through OAuth. The backend exchanges the code for an access token and stores it on your user record.
3. The dashboard lists your repositories via `GET /github/repos`.
4. You select a repo and the frontend calls `POST /analyze` with the clone URL.
5. The backend shallow-clones the repo (`depth=1`), verifies it's a Python project, runs all analyses, and deletes the clone.
6. The dashboard renders the five report sections in tabs; you can download a Markdown report.

## Analyses

| Section | Method |
|---------|--------|
| **Cyclomatic complexity** | Per-function complexity via [radon](https://radon.readthedocs.io)'s `cc_visit`. |
| **Duplicate detection** | TF-IDF vectorization + cosine similarity (scikit-learn); reports the top 5 most-similar file pairs. |
| **Time complexity** | AST-based Big-O estimate from maximum loop-nesting depth; recursive functions are flagged as `O(2^n)`. |
| **Bad practices** | AST scan for bare `except`, `global` usage, mutable default arguments, functions with >5 arguments, wildcard imports, and `eval`/`exec` calls. |
| **Test coverage** | Detects test files by naming convention (`test_*.py`, `*_test.py`). |

## Tech stack

- **Backend** — FastAPI, SQLAlchemy, Pydantic / pydantic-settings, GitPython, radon, scikit-learn, python-jose (JWT), bcrypt, httpx. PostgreSQL via psycopg (SQLite also supported for local dev).
- **Frontend** — Next.js 16, React 19, TypeScript, Tailwind CSS v4, Axios, lucide-react.

## Project layout

```
backend/
  main.py              # app init, CORS, router registration, DB table creation
  core/                # config (env), database (engine/session), security (JWT + bcrypt)
  models/user.py       # User SQLAlchemy model
  schemas/             # auth + analysis Pydantic models
  services/            # auth (user CRUD) + analysis (clone, all analyzers, orchestrator)
  routers/             # auth, github (OAuth), analyze
  tests/               # pytest suite
frontend/app/
  context/AuthContext.tsx   # JWT auth provider + useAuth hook
  api.ts                    # Axios instance with bearer-token interceptor
  page.tsx                  # landing page
  login/ signup/            # auth forms
  dashboard/page.tsx        # connect panel, repo list, results
  components/analysis/      # tab components + ReportViewer
  components/ui/             # Button, Input, Alert
```

## Getting started

### Prerequisites

- Python 3.12+
- Node.js (see `frontend/.nvmrc`)
- A [GitHub OAuth App](https://github.com/settings/developers) with callback URL `http://localhost:8000/github/callback`

### Backend

Run from the project root — the backend is a package, so it's invoked with the dotted module path.

```bash
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # then fill in the values below
uvicorn backend.main:app --reload      # http://localhost:8000
```

Required `.env` values:

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET` | Signing key for auth tokens — use a long random string. |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | From your GitHub OAuth App. |
| `GITHUB_REDIRECT_URI` | Defaults to `http://localhost:8000/github/callback`. |
| `FRONTEND_URL` | Defaults to `http://localhost:3000`. |
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME` (URL-encode special characters in the password — `@` becomes `%40`). Use `sqlite:///./analyzer.db` for local dev. |

Database tables are created automatically on startup.

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
```

Other scripts: `npm run build`, `npm run lint`.

> **Next.js 16 note:** this project pins Next.js 16.2.6, which has breaking changes from earlier versions. Consult `frontend/node_modules/next/dist/docs/` for current API conventions before modifying frontend code.

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/signup` | Create account, returns JWT. |
| `POST` | `/auth/login` | Authenticate, returns JWT. |
| `GET`  | `/auth/me` | Current user (requires bearer token). |
| `GET`  | `/github/connect-url` | Returns the GitHub OAuth authorization URL. |
| `GET`  | `/github/callback` | OAuth callback; stores token, redirects to the dashboard. |
| `GET`  | `/github/repos` | Lists the connected account's repositories. |
| `POST` | `/analyze` | Clones and analyzes a repo. Returns `400` for non-Python repos, `500` for other errors. |
| `POST` | `/analyze/export` | Renders an analysis result as a downloadable Markdown report. |

## Tests

```bash
pytest        # from the project root
```

The suite in `backend/tests/` covers the auth flow and the analysis-service functions.

## Roadmap

- Support private-repo cloning by injecting the stored GitHub token into the clone URL.
- Persist analysis results per user (`AnalysisResult` model + history endpoint and page).
- Add CSRF protection to the GitHub OAuth `state` parameter (currently just the user ID).
- Rate-limit `/analyze`, since cloning is expensive.
- Add a "disconnect GitHub" endpoint and paginate `/github/repos` beyond 50 repos.
- Docker Compose setup for one-command local startup.

## License

No license specified.
