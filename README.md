# CodeScope

A fullstack Python code-analysis tool. Connect your GitHub account, pick a repository, and get a structured health report — complexity, duplication, maintainability, security, dead code, type coverage, and a behavioural read of the repository's git history — rendered in a tabbed dashboard, tracked over time, and postable straight onto your pull requests.

## What makes it different

Most static-analysis tools measure code as it exists *right now*. They cannot tell you that a file changed 200 times last quarter, or that one person wrote 90% of your payment module.

CodeScope reads the commit log as well as the code. That unlocks a class of metrics a snapshot-based tool structurally cannot produce:

- **Hotspots** — `churn × complexity`. A complicated file nobody touches is cheap to leave alone; a complicated file that changes every week is where defects breed.
- **Change coupling** — files habitually committed together. These are implicit dependencies the import graph cannot see.
- **Bus factor** — how much of the codebase walks out of the door with one person.
- **Trends** — every run stores a metric snapshot, so the second analysis of a repository tells you what got *worse*, not just what is.

## Analyses

Three **core modules** determine the weighted 0–100 health score:

| Module | Method |
|--------|--------|
| **Cyclomatic complexity** | Per-function McCabe complexity over the AST (radon's `cc_visit`). Weight: 30%. |
| **Duplicate detection** | Winnowing: AST token normalization → k-gram hashing → fingerprint selection → pairwise Jaccard similarity. Reports duplicate line ranges, not just file pairs. Weight: 30%. |
| **Maintainability** | Halstead metrics derived from AST operators/operands, combined into a Coleman-Oman Maintainability Index normalized to 0–100. Weight: 40%. |

Five **supporting modules** report alongside it:

| Module | Method |
|--------|--------|
| **Behavioural analysis** | `git log --numstat` → churn with 180-day exponential time decay, log-normalized churn × complexity hotspots, change coupling by conditional co-change probability, and bus factor. |
| **Security** | AST vulnerability rules (`eval`, `shell=True`, unsafe deserialization, disabled TLS verification, string-built SQL, weak hashes), hardcoded-secret detection via name heuristics + provider token signatures + Shannon entropy, and dependency CVEs from the [OSV.dev](https://osv.dev) advisory database. |
| **Dead code** | Whole-project reachability analysis. Self-references are discounted, so a recursive function nobody calls is still reported. Every finding carries a confidence level. |
| **Type hint coverage** | PEP 484 coverage measured per *annotatable slot* — one per parameter plus one for the return — pooled repo-wide rather than averaged per file. |
| **Bad practices** | Auxiliary AST linter: bare `except`, mutable default arguments, wildcard imports, `global` usage, excessive arguments. |

### Scoring notes

- **Security score** uses penalty *density* per 1,000 lines for code findings, so the score is comparable between a 500-line script and a 50,000-line service. Dependency advisories are counted once per *package* at its worst severity — one version bump clears every CVE against it.
- **Findings in test code** are labelled and dropped one severity rung. `pickle.loads` and `verify=False` in a test suite are usually exercising the behaviour, not shipping it.
- **Churn** is exponentially time-decayed with a 180-day half-life, anchored to the newest commit rather than wall-clock time, so the same clone always produces the same numbers.

## Pull request integration

Point a GitHub webhook at CodeScope and every pull request gets analysed automatically:

1. GitHub delivers a `pull_request` event; the HMAC signature is verified.
2. The head commit's status goes to *pending*, and the request returns immediately — the work moves to a background task.
3. `refs/pull/<n>/head` is analysed and diffed against the repository's last completed run.
4. A **sticky comment** is posted, or edited in place on subsequent pushes, showing the metric deltas.
5. The commit status resolves through a quality gate.

The gate blocks on only two things — a **critical or high severity security finding**, or a **health score drop of 5+ points**. Smaller regressions are reported in the comment but pass, because a build that goes red over 0.4 complexity gets ignored within a week.

## Screenshots

<!-- Add screenshots of the Overview, Hotspots and Trends tabs here. -->

## Tech stack

- **Backend** — FastAPI, SQLAlchemy, Pydantic / pydantic-settings, GitPython, radon, python-jose (JWT), bcrypt, httpx. PostgreSQL via psycopg; SQLite works for local development.
- **Frontend** — Next.js 16, React 19, TypeScript, Tailwind CSS v4, Axios, lucide-react.

Every analysis algorithm is implemented in this repository. The only third-party algorithmic dependency is radon, used for cyclomatic complexity; Winnowing, Halstead/MI, churn, hotspots, coupling, bus factor, reachability, entropy analysis and the security rules are all hand-written over Python's `ast` module.

## Project layout

```
backend/
  main.py                    # app init, CORS, routers, schema migration on startup
  core/                      # config (env), database (engine/session), security (JWT + bcrypt)
  models/                    # User, Analysis (run record + metric snapshot)
  schemas/                   # auth + analysis Pydantic models
  services/
    analysis.py              # orchestrator: clone -> parse -> measure -> score
    complexity.py            # McCabe cyclomatic complexity
    duplication.py           # Winnowing fingerprinting
    maintainability.py       # Halstead metrics + Maintainability Index
    history.py               # churn, hotspots, change coupling, bus factor
    security.py              # AST rules, secret detection, OSV.dev advisories
    deadcode.py              # whole-project reachability
    typehints.py             # PEP 484 annotation coverage
    trends.py                # metric snapshots and regression diffs
    practices.py             # auxiliary bad-practice linter
    github_auth.py           # GitHub token lifecycle and refresh
    auth.py                  # user CRUD
  routers/                   # auth, github, analyze, history, webhooks, admin
  tests/                     # pytest suite (193 tests)
frontend/app/
  context/AuthContext.tsx    # JWT auth provider + useAuth hook
  api.ts                     # Axios instance with bearer-token interceptor
  dashboard/page.tsx         # connect panel, repo list, results
  components/analysis/       # ReportViewer + one component per tab
  components/ui/             # Button, Input, Alert
```

## Getting started

### Prerequisites

- Python 3.12+
- Node.js 20+ (see `frontend/.nvmrc`)
- A [GitHub App](https://github.com/settings/apps) or [OAuth App](https://github.com/settings/developers) with callback URL `http://localhost:8000/github/callback`

### Quick start

```bash
make install    # backend deps + frontend deps
make dev        # backend on :8000, frontend on :3000
```

`make dev` runs both and stops both on Ctrl+C. Individual targets: `make backend`, `make frontend`, `make test`.

### Manual setup

The backend is a Python package, so it is invoked from the project root with a dotted module path.

```bash
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env    # then fill in the values below
uvicorn backend.main:app --reload       # http://localhost:8000
```

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

### Configuration

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET` | Signing key for auth tokens — use a long random string. |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | From your GitHub App or OAuth App. |
| `GITHUB_REDIRECT_URI` | Defaults to `http://localhost:8000/github/callback`. |
| `FRONTEND_URL` | Defaults to `http://localhost:3000`. |
| `DATABASE_URL` | `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME` (URL-encode special characters — `@` becomes `%40`), or `sqlite:///./analyzer.db` for local dev. |
| `GITHUB_WEBHOOK_SECRET` | Enables the PR endpoint. Without it `/webhooks/github` returns 503 rather than trusting unsigned payloads. |
| `HISTORY_CLONE_DEPTH` | Commits fetched for behavioural analysis. Default 300. A depth of 1 makes churn, hotspots, coupling and bus factor impossible. |
| `ENABLE_DEPENDENCY_SCAN` | Check dependencies against OSV.dev. Requires outbound network access. Default true. |
| `ADMIN_EMAILS` | Comma-separated emails auto-promoted to admin on startup. |

Tables are created and migrated automatically on startup.

> **GitHub App vs OAuth App:** a GitHub App issues short-lived user tokens (`ghu_`, ~8 hours) with a rotating refresh token; `services/github_auth.py` renews them transparently. An OAuth App issues non-expiring tokens (`gho_`); the expiry columns stay NULL and refreshing is skipped. Both work.

> **Next.js 16 note:** this project pins Next.js 16.2.6, which has breaking changes from earlier versions. Consult `frontend/node_modules/next/dist/docs/` before modifying frontend code.

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/signup` | Create account, returns JWT. |
| `POST` | `/auth/login` | Authenticate, returns JWT. |
| `GET`  | `/auth/me` | Current user. |
| `GET`  | `/github/connect-url` | GitHub authorization URL. |
| `GET`  | `/github/callback` | OAuth callback; stores tokens, redirects to the dashboard. |
| `GET`  | `/github/repos` | Repositories for the connected account. |
| `POST` | `/github/disconnect` | Revoke the token and unlink the account. |
| `POST` | `/analyze` | Clone and analyze a repository. `400` for non-Python repos. |
| `POST` | `/analyze/export` | Render a result as a downloadable Markdown report. |
| `GET`  | `/analyses` | Past runs for the current user. |
| `GET`  | `/analyses/trend` | Metric history for one repository. |
| `GET`  | `/analyses/compare` | Diff two stored runs. |
| `POST` | `/webhooks/github` | GitHub webhook receiver (HMAC-verified). |
| `POST` | `/webhooks/pull-request/check` | Run the PR pipeline on demand. |
| `GET`  | `/admin/stats` · `/admin/users` · `/admin/analyses` | Admin monitoring. |

## Tests

```bash
make test                              # or: python -m pytest backend/tests -q
```

193 tests covering the auth flow, every analysis module, the token refresh path, the history endpoints and the webhook pipeline.

## Continuous integration

`.github/workflows/ci.yml` runs two parallel jobs on every push and pull request to `main`:

| Job | Steps |
|-----|-------|
| **Backend tests** | Python 3.12 → install `backend/requirements.txt` → `pytest backend/tests` |
| **Frontend lint and build** | Node from `.nvmrc` → `npm ci` → `npm run lint` → `npm run build` |

**No setup is required.** Push the workflow file and GitHub Actions picks it up on the next push — no secrets, no runners to register, no database service. The backend job points `DATABASE_URL` at a scratch SQLite file, because the app's `lifespan` creates tables against the configured database on startup even though every request is overridden onto SQLite in tests. `ENABLE_DEPENDENCY_SCAN` is switched off so the suite makes no network calls to OSV.dev.

Both jobs cache their dependencies, and `concurrency` cancels a run when a newer commit lands on the same branch.

To require green CI before merging: **Settings → Branches → Add branch protection rule** for `main`, tick *Require status checks to pass*, and select `Backend tests` and `Frontend lint and build` (they appear in the list after the workflow has run at least once).

Add a status badge by putting this at the top of this file, replacing `OWNER/REPO`:

```markdown
![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)
```

## Roadmap

- Move analysis to a background job queue with progress streaming; it currently runs synchronously inside the request.
- Support private-repo cloning by injecting the stored GitHub token into the clone URL.
- Build a control-flow graph to enable true `E − N + 2P` McCabe, dataflow analysis and taint tracking.
- Cache analysis results by git blob SHA so re-runs only process changed files.
- SARIF export, so findings render in GitHub's Security tab.
- A `.codescope.yml` for configurable thresholds and path exclusions.
- Import-graph panel with Tarjan SCC circular-import detection.

## License

No license specified.
