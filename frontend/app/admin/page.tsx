"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Loader2, Shield, Users, Activity, GitFork, Trash2,
  CheckCircle2, XCircle, BarChart3,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import api, { apiErrorMessage } from "../api";
import Alert from "../components/ui/Alert";

interface AdminUser {
  id: number;
  email: string;
  username: string;
  role: string;
  github_username: string | null;
  created_at: string | null;
}
interface AdminAnalysis {
  id: number;
  user_id: number;
  username: string | null;
  repo_name: string;
  repo_url: string;
  status: string;
  health_score: number | null;
  created_at: string | null;
}
interface Stats {
  total_users: number;
  admin_users: number;
  github_connected: number;
  total_analyses: number;
  completed_analyses: number;
  failed_analyses: number;
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

function healthColor(score: number | null) {
  if (score === null) return "bg-slate-700 text-slate-300";
  if (score >= 65) return "bg-green-500/15 text-green-400";
  if (score >= 50) return "bg-amber-500/15 text-amber-400";
  return "bg-red-500/15 text-red-400";
}

function StatCard({ Icon, label, value, hint }: { Icon: React.ElementType; label: string; value: number; hint?: string }) {
  return (
    <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
      <div className="flex items-center gap-1.5 text-slate-500 mb-1.5">
        <Icon className="w-3.5 h-3.5" />
        <span className="text-xs">{label}</span>
      </div>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
    </div>
  );
}

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [stats, setStats] = useState<Stats | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [analyses, setAnalyses] = useState<AdminAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAll = useCallback(async () => {
    await Promise.resolve(); // defer so effect callers don't set state synchronously
    setLoading(true);
    try {
      const [s, u, a] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/admin/users"),
        api.get("/admin/analyses"),
      ]);
      setStats(s.data);
      setUsers(u.data);
      setAnalyses(a.data);
      setError("");
    } catch (err) {
      setError(apiErrorMessage(err, "Failed to load admin data."));
    } finally {
      setLoading(false);
    }
  }, []);

  // Access guard: only admins may view this page.
  useEffect(() => {
    if (authLoading) return;
    if (!user) router.push("/login");
    else if (user.role !== "admin") router.push("/dashboard");
  }, [authLoading, user, router]);

  useEffect(() => {
    if (!authLoading && user?.role === "admin") {
      const run = async () => {
        await Promise.resolve();
        loadAll();
      };
      void run();
    }
  }, [authLoading, user?.role, loadAll]);

  const deleteUser = async (u: AdminUser) => {
    if (!window.confirm(`Delete user "${u.username}"? This also removes their analyses.`)) return;
    try {
      await api.delete(`/admin/users/${u.id}`);
      loadAll();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not delete user."));
    }
  };

  if (authLoading || !user || user.role !== "admin") {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-10 space-y-8">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-amber-500/15">
          <Shield className="w-5 h-5 text-amber-400" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">Admin Dashboard</h1>
          <p className="text-slate-400 text-sm">Manage users and monitor analyses across the platform.</p>
        </div>
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      {loading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
        </div>
      ) : (
        <>
          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatCard Icon={Users} label="Total Users" value={stats.total_users} />
              <StatCard Icon={Shield} label="Admins" value={stats.admin_users} />
              <StatCard Icon={GitFork} label="GitHub Linked" value={stats.github_connected} />
              <StatCard Icon={Activity} label="Analyses" value={stats.total_analyses} />
              <StatCard Icon={CheckCircle2} label="Completed" value={stats.completed_analyses} />
              <StatCard Icon={XCircle} label="Failed" value={stats.failed_analyses} />
            </div>
          )}

          {/* Users */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Users className="w-4 h-4" /> Manage Users
            </h2>
            <div className="rounded-2xl border border-slate-800 overflow-x-auto">
              <table className="w-full text-sm min-w-[640px]">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">User</th>
                    <th className="px-4 py-3 text-left font-medium">Email</th>
                    <th className="px-4 py-3 text-left font-medium">Role</th>
                    <th className="px-4 py-3 text-left font-medium">GitHub</th>
                    <th className="px-4 py-3 text-left font-medium">Joined</th>
                    <th className="px-4 py-3 text-right font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-800/30">
                      <td className="px-4 py-3 text-slate-200">{u.username}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{u.email}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${u.role === "admin" ? "bg-amber-500/15 text-amber-400" : "bg-slate-700 text-slate-300"}`}>
                          {u.role}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-xs">{u.github_username ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{fmtDate(u.created_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => deleteUser(u)}
                          disabled={u.id === user.id || u.role === "admin"}
                          title={u.role === "admin" ? "Cannot delete an admin" : "Delete user"}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          <Trash2 className="w-3.5 h-3.5" /> Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Analyses */}
          <section className="space-y-3">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Monitor Analyses
            </h2>
            <div className="rounded-2xl border border-slate-800 overflow-x-auto">
              <table className="w-full text-sm min-w-[640px]">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-400">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Repository</th>
                    <th className="px-4 py-3 text-left font-medium">User</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium">Health</th>
                    <th className="px-4 py-3 text-left font-medium">When</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {analyses.length ? (
                    analyses.map((a) => (
                      <tr key={a.id} className="hover:bg-slate-800/30">
                        <td className="px-4 py-3 text-slate-200 truncate max-w-[220px]" title={a.repo_url}>{a.repo_name}</td>
                        <td className="px-4 py-3 text-slate-400 text-xs">{a.username ?? "—"}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${a.status === "completed" ? "bg-green-500/15 text-green-400" : "bg-red-500/15 text-red-400"}`}>
                            {a.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-0.5 rounded-md text-xs font-mono ${healthColor(a.health_score)}`}>
                            {a.health_score ?? "—"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-500 text-xs">{fmtDate(a.created_at)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="px-4 py-10 text-center text-slate-500 text-sm">No analyses recorded yet</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
