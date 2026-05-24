# CodeScope

Intelligent Python code analyzer. Connect your GitHub, pick a repo, get a full report.

---

## TODO

### Setup
- [ ] Create GitHub OAuth App at github.com/settings/developers (callback: `http://localhost:8000/github/callback`)
- [ ] Copy `backend/.env.example` → `backend/.env` and fill in `JWT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`
- [ ] `pip install -r backend/requirements.txt`
- [ ] `cd frontend && npm install`

### Backend
- [ ] Support private repo cloning (inject GitHub token into clone URL: `https://<token>@github.com/...`)
- [ ] Save analysis results to DB per user (add `AnalysisResult` model + history endpoint)
- [ ] Add CSRF protection to GitHub OAuth `state` param (currently just user ID)
- [ ] Add rate limiting on `/analyze` (cloning is expensive)
- [ ] Disconnect GitHub endpoint (`DELETE /github/connection`)
- [ ] Paginate `GET /github/repos` beyond 50 repos

### Frontend
- [ ] Analysis history page — list past runs per user
- [ ] Show full file path on hover in results cards (currently truncated to filename)
- [ ] Redirect unauthenticated users back to original destination after login
- [ ] Toast notifications for GitHub connect success/failure
- [ ] Loading skeleton for repo list

### Quality
- [ ] Add backend tests (pytest) for analysis service functions
- [ ] Add `.env` to `.gitignore`
- [ ] Docker Compose setup (frontend + backend + optional Postgres)
- [ ] Switch from SQLite to PostgreSQL for production
