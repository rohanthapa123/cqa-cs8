"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2, Lock, Star, RefreshCw, ChevronRight, GitFork, Search, BarChart3, Unlink } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import api, { apiErrorMessage } from "../api";
import { AnalysisReport } from "../types/analysis";
import ReportViewer from "../components/analysis/ReportViewer";
import Button from "../components/ui/Button";
import Alert from "../components/ui/Alert";

interface Repo {
  name: string;
  full_name: string;
  html_url: string;
  clone_url: string;
  description: string | null;
  language: string | null;
  updated_at: string;
  private: boolean;
  stargazers_count: number;
}

// ---------- sub-components ----------

function RepoCard({
  repo,
  selected,
  disabled,
  onClick,
}: {
  repo: Repo;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={[
        "w-full text-left p-4 rounded-xl border transition-all group",
        selected
          ? "border-indigo-500/50 bg-indigo-500/5"
          : "border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900",
        "disabled:opacity-50 disabled:cursor-not-allowed",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-1.5">
            {repo.private && <Lock className="w-3 h-3 text-slate-500 shrink-0" />}
            <span className="text-sm font-medium text-slate-200 truncate">{repo.name}</span>
          </div>
          {repo.description && (
            <p className="text-xs text-slate-500 truncate">{repo.description}</p>
          )}
          <div className="flex items-center gap-3 text-xs">
            {repo.language && <span className="text-slate-400">{repo.language}</span>}
            {repo.stargazers_count > 0 && (
              <span className="flex items-center gap-1 text-slate-600">
                <Star className="w-3 h-3" />{repo.stargazers_count}
              </span>
            )}
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-slate-400 shrink-0 mt-0.5 transition-colors" />
      </div>
    </button>
  );
}

function GitHubConnectCard({ loading, onConnect }: { loading: boolean; onConnect: () => void }) {
  return (
    <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/50 space-y-5 text-center">
      <div className="w-12 h-12 rounded-2xl bg-slate-800 flex items-center justify-center mx-auto">
        <GitFork className="w-6 h-6 text-slate-300" />
      </div>
      <div>
        <h3 className="font-semibold text-white">Connect GitHub</h3>
        <p className="text-sm text-slate-400 mt-1">Link your account to browse and analyze repositories.</p>
      </div>
      <Button onClick={onConnect} loading={loading} fullWidth variant="secondary">
        {loading ? "Redirecting…" : "Connect GitHub"}
      </Button>
    </div>
  );
}

function RepoPanel({
  repos,
  reposLoading,
  reposError,
  connectLoading,
  analyzing,
  selectedRepo,
  hasGithub,
  onConnect,
  onRefresh,
  onSelectRepo,
}: {
  repos: Repo[];
  reposLoading: boolean;
  reposError: string;
  connectLoading: boolean;
  analyzing: boolean;
  selectedRepo: Repo | null;
  hasGithub: boolean;
  onConnect: () => void;
  onRefresh: () => void;
  onSelectRepo: (repo: Repo) => void;
}) {
  const [search, setSearch] = useState("");
  const filtered = repos.filter(
    (r) =>
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      (r.description ?? "").toLowerCase().includes(search.toLowerCase())
  );

  if (!hasGithub) return <GitHubConnectCard loading={connectLoading} onConnect={onConnect} />;

  return (
    <>
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Repositories</h2>
        <button
          onClick={onRefresh}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${reposLoading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
        <input
          type="text"
          placeholder="Search repos…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
        />
      </div>

      {reposError && <Alert variant="error">{reposError}</Alert>}

      {reposLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
        </div>
      ) : (
        <div className="space-y-1.5 max-h-[62vh] overflow-y-auto pr-0.5">
          {filtered.map((repo) => (
            <RepoCard
              key={repo.full_name}
              repo={repo}
              selected={selectedRepo?.full_name === repo.full_name}
              disabled={analyzing}
              onClick={() => onSelectRepo(repo)}
            />
          ))}
          {filtered.length === 0 && (
            <p className="text-center text-sm text-slate-500 py-10">No repositories found</p>
          )}
        </div>
      )}
    </>
  );
}

// ---------- main content ----------

function DashboardContent() {
  const { user, loading: authLoading, refreshUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [repos, setRepos] = useState<Repo[]>([]);
  const [reposLoading, setReposLoading] = useState(false);
  const [connectLoading, setConnectLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState<Repo | null>(null);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [analyzeError, setAnalyzeError] = useState("");
  const [reposError, setReposError] = useState("");
  const [disconnecting, setDisconnecting] = useState(false);

  const loadRepos = useCallback(async () => {
    await Promise.resolve(); // defer so effect callers don't set state synchronously
    setReposLoading(true);
    try {
      const { data } = await api.get("/github/repos");
      setRepos(data);
      setReposError("");
    } catch (err) {
      setRepos([]);
      setReposError(apiErrorMessage(err, "Could not load repositories. Try reconnecting GitHub."));
    } finally {
      setReposLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && !user) router.push("/login");
  }, [authLoading, user, router]);

  useEffect(() => {
    const github = searchParams.get("github");
    const err = searchParams.get("error");
    if (github === "connected") {
      refreshUser().then(() => loadRepos());
      window.history.replaceState({}, "", "/dashboard");
    }
    if (err) window.history.replaceState({}, "", "/dashboard");
  }, [searchParams, refreshUser, loadRepos]);

  useEffect(() => {
    const run = async () => {
      await Promise.resolve();
      if (user?.github_username) loadRepos();
    };
    void run();
  }, [user?.github_username, loadRepos]);

  const connectGithub = async () => {
    setConnectLoading(true);
    try {
      const { data } = await api.get("/github/connect-url");
      window.location.href = data.url;
    } catch {
      setConnectLoading(false);
    }
  };

  const analyzeRepo = async (repo: Repo) => {
    setSelectedRepo(repo);
    setReport(null);
    setAnalyzeError("");
    setAnalyzing(true);
    try {
      const { data } = await api.post("/analyze", { repo_url: repo.html_url });
      setReport(data);
    } catch (err) {
      setAnalyzeError(apiErrorMessage(err, "Analysis failed. Make sure this is a Python repository."));
    } finally {
      setAnalyzing(false);
    }
  };

  const clearReport = () => {
    setReport(null);
    setSelectedRepo(null);
    setAnalyzeError("");
  };

  const disconnectGithub = async () => {
    setDisconnecting(true);
    try {
      await api.post("/github/disconnect");
      await refreshUser();
      setRepos([]);
      clearReport();
    } catch {
      // ignore; UI stays as-is
    } finally {
      setDisconnecting(false);
    }
  };

  if (authLoading || !user) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="mb-10 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 text-sm mt-1">
            Hello, <span className="text-slate-200">{user.username}</span>
            {user.github_username && (
              <span className="inline-flex items-center gap-1 ml-2">
                · <GitFork className="w-3.5 h-3.5" /> {user.github_username}
              </span>
            )}
          </p>
        </div>
        {user.github_username && (
          <button
            onClick={disconnectGithub}
            disabled={disconnecting}
            title="Unlink this GitHub account so you can connect a different one"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border border-slate-700 text-slate-300 hover:bg-slate-800 hover:text-white transition-colors disabled:opacity-50 shrink-0"
          >
            {disconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unlink className="w-3.5 h-3.5" />}
            <span>{disconnecting ? "Disconnecting…" : "Disconnect GitHub"}</span>
          </button>
        )}
      </div>

      <div className="grid lg:grid-cols-[360px_1fr] gap-8">
        {/* Left: repo panel */}
        <aside className="space-y-4">
          <RepoPanel
            repos={repos}
            reposLoading={reposLoading}
            reposError={reposError}
            connectLoading={connectLoading}
            analyzing={analyzing}
            selectedRepo={selectedRepo}
            hasGithub={!!user.github_username}
            onConnect={connectGithub}
            onRefresh={loadRepos}
            onSelectRepo={analyzeRepo}
          />
        </aside>

        {/* Right: analysis panel.
            `min-w-0` is load-bearing: a grid item defaults to `min-width: auto`,
            so without it the column refuses to shrink below its widest child and
            wide report content pushes the whole page into horizontal scroll. */}
        <div className="min-h-[400px] min-w-0">
          {!selectedRepo && !analyzing && !report && (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center space-y-3 rounded-2xl border border-dashed border-slate-800">
              <BarChart3 className="w-8 h-8 text-slate-700" />
              <p className="text-slate-500 text-sm">
                {user.github_username ? "Select a repository to run analysis" : "Connect GitHub to get started"}
              </p>
            </div>
          )}

          {analyzing && (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] space-y-4">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
              <div className="text-center">
                <p className="text-slate-200 font-medium">Analyzing {selectedRepo?.name}…</p>
                <p className="text-sm text-slate-500 mt-1">Cloning, parsing, and computing metrics</p>
              </div>
            </div>
          )}

          {analyzeError && !analyzing && (
            <div className="space-y-3">
              <Alert variant="error">{analyzeError}</Alert>
              <button onClick={clearReport} className="text-sm text-slate-500 hover:text-slate-300 transition-colors">
                ← Back
              </button>
            </div>
          )}

          {report && !analyzing && (
            <ReportViewer
              repoName={selectedRepo?.name ?? ""}
              report={report}
              onClose={clearReport}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
        </div>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}
