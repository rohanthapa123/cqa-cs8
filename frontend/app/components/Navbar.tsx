"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Code2, LogOut, LayoutDashboard, GitFork, Shield } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  return (
    <nav className="fixed top-0 inset-x-0 z-50 border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 ring-1 ring-indigo-500/20 group-hover:bg-indigo-500/20 transition-colors">
            <Code2 className="w-4 h-4 text-indigo-400" />
          </div>
          <span className="font-semibold text-slate-200">CodeAnalysis</span>
        </Link>

        <div className="flex items-center gap-2">
          {user ? (
            <>
              <span className="text-sm text-slate-400 hidden sm:flex items-center gap-1.5 mr-1">
                {user.github_username
                  ? <><GitFork className="w-3.5 h-3.5" />{user.github_username}</>
                  : user.username}
              </span>
              {user.role === "admin" && (
                <Link
                  href="/admin"
                  className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 transition-colors"
                >
                  <Shield className="w-4 h-4" />
                  <span className="hidden sm:block">Admin</span>
                </Link>
              )}
              <Link
                href="/dashboard"
                className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                <LayoutDashboard className="w-4 h-4" />
                <span className="hidden sm:block">Dashboard</span>
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="px-4 py-1.5 text-sm rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
              >
                Log in
              </Link>
              <Link
                href="/signup"
                className="px-4 py-1.5 text-sm rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors font-medium"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
